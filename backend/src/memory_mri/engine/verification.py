from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from memory_mri.agents.base import AgentRunner
from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    AgentInputMemory,
    BenchmarkCase,
    ExecutionTrace,
    RepairProposal,
    RepairType,
    SupportValidityResult,
    VerificationRun,
    VerificationVerdict,
)


class VerificationEngine:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
        fake_baseline_path: Path | None = None,
        gpt_baseline_path: Path | None = None,
        openai_settings: OpenAISettings | None = None,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self.fake_baseline_path = (
            fake_baseline_path or artifacts_dir / "day1-mixed-baseline-summary.json"
        )
        self.gpt_baseline_path = gpt_baseline_path or artifacts_dir / "gpt-baseline-summary.json"
        self.openai_settings = openai_settings or OpenAISettings.from_env()

    def verify_original(
        self,
        proposal_id: str,
        *,
        runner_name: str = "fake",
    ) -> VerificationRun:
        return self._verify(proposal_id, runner_name=runner_name, scope="original")

    def verify_domain(
        self,
        proposal_id: str,
        *,
        runner_name: str = "fake",
    ) -> VerificationRun:
        return self._verify(proposal_id, runner_name=runner_name, scope="domain")

    def verify_full_benchmark(
        self,
        proposal_id: str,
        *,
        runner_name: str = "fake",
    ) -> VerificationRun:
        return self._verify(proposal_id, runner_name=runner_name, scope="full")

    def show_verification(self, verification_id: str) -> VerificationRun:
        verification = self.repository.get_verification_run(verification_id)
        if verification is None:
            raise ValueError(f"unknown verification run: {verification_id}")
        return verification

    def compare_benchmarks(self, before_path: Path, after_path: Path) -> dict[str, Any]:
        before = _load_summary(before_path)
        after = _load_summary(after_path)
        before_rows = _result_rows(before)
        after_rows = _result_rows(after)
        before_map = {row["scenario_id"]: row for row in before_rows}
        after_map = {row["scenario_id"]: row for row in after_rows}
        repaired_failures: list[str] = []
        new_regressions: list[str] = []
        unchanged_passes: list[str] = []
        unchanged_failures: list[str] = []
        action_changes: list[dict[str, Any]] = []

        for scenario_id in sorted(set(before_map) | set(after_map)):
            before_row = before_map.get(scenario_id)
            after_row = after_map.get(scenario_id)
            if before_row is None or after_row is None:
                continue
            if before_row.get("selected_action") != after_row.get(
                "selected_action"
            ) or before_row.get("passed") != after_row.get("passed"):
                action_changes.append(
                    {
                        "scenario_id": scenario_id,
                        "before_action": before_row.get("selected_action"),
                        "after_action": after_row.get("selected_action"),
                        "before_passed": before_row.get("passed"),
                        "after_passed": after_row.get("passed"),
                    }
                )
            if before_row.get("passed") is False and after_row.get("passed") is True:
                repaired_failures.append(scenario_id)
            elif before_row.get("passed") is True and after_row.get("passed") is False:
                new_regressions.append(scenario_id)
            elif before_row.get("passed") is True and after_row.get("passed") is True:
                unchanged_passes.append(scenario_id)
            elif before_row.get("passed") is False and after_row.get("passed") is False:
                unchanged_failures.append(scenario_id)

        return {
            "before": str(before_path),
            "after": str(after_path),
            "before_overall": _summary_overall(before),
            "after_overall": _summary_overall(after),
            "repaired_failures": repaired_failures,
            "new_regressions": new_regressions,
            "unchanged_passes": unchanged_passes,
            "unchanged_failures": unchanged_failures,
            "action_changes": action_changes,
        }

    def _verify(
        self,
        proposal_id: str,
        *,
        runner_name: str,
        scope: str,
    ) -> VerificationRun:
        proposal = self._get_proposal(proposal_id)
        before_path = self._baseline_path_for_runner(runner_name)
        if proposal.repair_type in {
            RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
            RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
        }:
            verification = self._build_not_applicable_verification(
                proposal=proposal,
                before_path=before_path,
                runner_name=runner_name,
            )
            self._persist_verification(verification, scope=scope)
            return verification
        if proposal.applied_version_id is None:
            raise ValueError("proposal must be applied before verification")

        applied_version = self.repository.get_memory_version(proposal.applied_version_id)
        if applied_version is None:
            raise ValueError("applied memory version is missing")

        cases = load_benchmark_cases(self.data_dir)
        for case in cases:
            self.repository.import_case(case)
        self.session.commit()

        runner = self._runner(runner_name)
        after_cases = self._cases_for_scope(
            cases=cases,
            proposal=proposal,
            applied_version=applied_version.memory_snapshot,
            scope=scope,
        )
        after_summary = self._run_cases(after_cases, runner)
        before_summary = _load_summary(before_path)

        verification_id = f"verification_{uuid4().hex}"
        verification_dir = self.artifacts_dir / "verifications" / verification_id
        verification_dir.mkdir(parents=True, exist_ok=True)
        after_summary_path = verification_dir / f"{scope}-after-summary.json"
        after_summary_path.write_text(json.dumps(after_summary, indent=2), encoding="utf-8")

        original_before = _scenario_outcome(before_summary, proposal.scenario_id)
        original_after = _scenario_outcome(after_summary, proposal.scenario_id)
        domain_before = _domain_slice(before_summary, proposal.domain.value)
        domain_after = _domain_slice(after_summary, proposal.domain.value)
        full_before = _summary_overall(before_summary)
        full_after = _summary_overall(after_summary)
        changed = self.compare_benchmarks(before_path, after_summary_path)
        support = self._support_validity_result(proposal, original_after)
        verification = VerificationRun(
            verification_id=verification_id,
            proposal_id=proposal.proposal_id,
            applied_version_id=proposal.applied_version_id,
            investigation_id=proposal.investigation_id,
            scenario_id=proposal.scenario_id,
            domain=proposal.domain,
            model=runner.model_name,
            prompt_version=runner.prompt_version,
            before_benchmark_id=str(before_path),
            after_benchmark_id=str(after_summary_path),
            original_case_before=original_before,
            original_case_after=original_after,
            domain_before=domain_before,
            domain_after=domain_after,
            full_before=full_before,
            full_after=full_after,
            repaired_failures=changed["repaired_failures"],
            persistent_failures=changed["unchanged_failures"],
            new_regressions=changed["new_regressions"],
            unchanged_passes=changed["unchanged_passes"],
            unchanged_failures=changed["unchanged_failures"],
            action_changes=changed["action_changes"],
            tool_call_changes=_tool_call_changes(before_summary, after_summary),
            support_validity_result=support,
            infrastructure_errors=after_summary["infrastructure_errors"],
            token_usage=after_summary["totals"]["token_usage"],
            latency=after_summary["totals"]["latency"],
            verdict=self._classify_verdict(
                proposal=proposal,
                original_after=original_after,
                repaired_failures=changed["repaired_failures"],
                new_regressions=changed["new_regressions"],
                support=support,
                infrastructure_errors=after_summary["infrastructure_errors"],
            ),
            created_at=datetime.now(timezone.utc),
        )
        self._persist_verification(verification, scope=scope)
        return verification

    def _build_not_applicable_verification(
        self,
        *,
        proposal: RepairProposal,
        before_path: Path,
        runner_name: str,
    ) -> VerificationRun:
        before_summary = _load_summary(before_path)
        original_before = _scenario_outcome(before_summary, proposal.scenario_id)
        support = SupportValidityResult(
            decision_still_supported=False,
            outcome_correct=False,
            requires_human_review=True,
            support_explanation=(
                "Memory repair is not applicable for prompt or policy escalation proposals."
            ),
        )
        return VerificationRun(
            verification_id=f"verification_{uuid4().hex}",
            proposal_id=proposal.proposal_id,
            applied_version_id=proposal.applied_version_id,
            investigation_id=proposal.investigation_id,
            scenario_id=proposal.scenario_id,
            domain=proposal.domain,
            model=self._runner(runner_name).model_name,
            prompt_version=self._runner(runner_name).prompt_version,
            before_benchmark_id=str(before_path),
            after_benchmark_id="not-applicable",
            original_case_before=original_before,
            original_case_after=original_before,
            domain_before=_domain_slice(before_summary, proposal.domain.value),
            domain_after=_domain_slice(before_summary, proposal.domain.value),
            full_before=_summary_overall(before_summary),
            full_after=_summary_overall(before_summary),
            repaired_failures=[],
            persistent_failures=[proposal.scenario_id] if not original_before.get("passed") else [],
            new_regressions=[],
            unchanged_passes=[proposal.scenario_id] if original_before.get("passed") else [],
            unchanged_failures=[proposal.scenario_id] if not original_before.get("passed") else [],
            action_changes=[],
            tool_call_changes=[],
            support_validity_result=support,
            infrastructure_errors=[],
            token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            latency={"total_latency_ms": 0},
            verdict=VerificationVerdict.MEMORY_REPAIR_NOT_APPLICABLE,
            created_at=datetime.now(timezone.utc),
        )

    def _cases_for_scope(
        self,
        *,
        cases: list[BenchmarkCase],
        proposal: RepairProposal,
        applied_version: list[AgentInputMemory],
        scope: str,
    ) -> list[BenchmarkCase]:
        if scope == "original":
            selected = [case for case in cases if case.scenario.id == proposal.scenario_id]
        elif scope == "domain":
            selected = [case for case in cases if case.scenario.domain == proposal.domain]
        else:
            selected = list(cases)
        updated: list[BenchmarkCase] = []
        for case in selected:
            if case.scenario.id == proposal.scenario_id:
                updated.append(self._apply_version_to_case(case, applied_version))
            else:
                updated.append(case.model_copy(deep=True))
        return updated

    def _apply_version_to_case(
        self,
        case: BenchmarkCase,
        applied_version: list[AgentInputMemory],
    ) -> BenchmarkCase:
        updated_case = case.model_copy(deep=True)
        memory_lookup = {memory.id: memory for memory in updated_case.memories}
        for snapshot_memory in applied_version:
            existing = memory_lookup.get(snapshot_memory.memory_id)
            if existing is None:
                continue
            existing.entity_id = snapshot_memory.entity_id
            existing.content = snapshot_memory.content
            existing.source = snapshot_memory.source
            existing.created_at = snapshot_memory.created_at
            existing.valid_from = snapshot_memory.valid_from
            existing.valid_until = snapshot_memory.valid_until
            existing.status = snapshot_memory.status
            existing.confidence = snapshot_memory.confidence
            existing.retrieval_priority = snapshot_memory.retrieval_priority
            existing.supersedes = list(snapshot_memory.supersedes)
            existing.tags = list(snapshot_memory.tags)
            existing.operational_metadata = dict(snapshot_memory.operational_metadata)
        return updated_case

    def _run_cases(self, cases: list[BenchmarkCase], runner: AgentRunner) -> dict[str, Any]:
        traces: list[ExecutionTrace] = []
        for case in cases:
            try:
                trace = runner.run_scenario(case.scenario, case.memories)
            except OpenAIRunnerError as exc:
                if exc.trace is None:
                    raise
                trace = exc.trace
            self.repository.save_trace(trace)
            traces.append(trace)
        self.session.commit()
        return _build_after_summary(cases, traces)

    def _support_validity_result(
        self,
        proposal: RepairProposal,
        original_after: dict[str, Any],
    ) -> SupportValidityResult:
        repaired = bool(original_after.get("repaired"))
        requires_human_review = bool(
            original_after.get("needs_human_review")
            or proposal.support_validity_result.requires_human_review
        )
        decision_still_supported = (
            repaired
            and proposal.support_validity_result.decision_still_supported
            and not requires_human_review
        )
        if repaired and not decision_still_supported:
            explanation = (
                "The expected action was produced after repair, but the proposal evidence does not "
                "support treating that action as a safe automated decision."
            )
        elif repaired:
            explanation = "The repaired result matches the expected action and remains supported."
        else:
            explanation = "The repaired version did not produce a supported correction."
        return SupportValidityResult(
            decision_still_supported=decision_still_supported,
            outcome_correct=repaired,
            requires_human_review=requires_human_review,
            support_explanation=explanation,
        )

    def _classify_verdict(
        self,
        *,
        proposal: RepairProposal,
        original_after: dict[str, Any],
        repaired_failures: list[str],
        new_regressions: list[str],
        support: SupportValidityResult,
        infrastructure_errors: list[dict[str, Any]],
    ) -> VerificationVerdict:
        if proposal.repair_type in {
            RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
            RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
        }:
            return VerificationVerdict.MEMORY_REPAIR_NOT_APPLICABLE
        if infrastructure_errors:
            return VerificationVerdict.VERIFICATION_INCONCLUSIVE
        repaired = bool(original_after.get("repaired"))
        if repaired and not support.decision_still_supported:
            return VerificationVerdict.UNSUPPORTED_BEHAVIOR_CHANGE
        if repaired and not new_regressions:
            return VerificationVerdict.VERIFIED_IMPROVEMENT
        if repaired and new_regressions:
            return VerificationVerdict.IMPROVEMENT_WITH_REGRESSIONS
        if not repaired and repaired_failures:
            return VerificationVerdict.VERIFICATION_INCONCLUSIVE
        if not repaired and original_after.get("action_changed"):
            return VerificationVerdict.NO_MEASURABLE_CHANGE
        return VerificationVerdict.FAILED_TO_REPAIR

    def _persist_verification(self, verification: VerificationRun, *, scope: str) -> None:
        self.repository.save_verification_run(verification)
        self.session.commit()
        verification_dir = self.artifacts_dir / "verifications" / verification.verification_id
        verification_dir.mkdir(parents=True, exist_ok=True)
        (verification_dir / f"{scope}-verification.json").write_text(
            verification.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _baseline_path_for_runner(self, runner_name: str) -> Path:
        return self.fake_baseline_path if runner_name == "fake" else self.gpt_baseline_path

    def _runner(self, runner_name: str) -> AgentRunner:
        if runner_name == "fake":
            return FakeAgentRunner()
        if runner_name == "openai":
            return OpenAIAgentRunner(self.openai_settings)
        raise ValueError(f"unsupported runner: {runner_name}")

    def _get_proposal(self, proposal_id: str) -> RepairProposal:
        proposal = self.repository.get_repair_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"unknown proposal: {proposal_id}")
        return proposal


def _load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"summary at {path} must be a JSON object")
    return payload


def _result_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in summary["scenario_results"]:
        domain = row.get("domain") or _domain_from_scenario_id(row["scenario_id"])
        if "actual_selected_action" in row:
            rows.append(
                {
                    "scenario_id": row["scenario_id"],
                    "domain": domain,
                    "selected_action": row["actual_selected_action"],
                    "expected_action": row["expected_action"],
                    "passed": row.get("passed"),
                    "trace_id": row.get("trace_id"),
                    "result_type": row.get("result_type", "evaluated"),
                    "error": row.get("error"),
                }
            )
        else:
            rows.append(
                {
                    "scenario_id": row["scenario_id"],
                    "domain": domain,
                    "selected_action": row["selected_action"],
                    "expected_action": row["expected_action"],
                    "passed": row.get("passed"),
                    "trace_id": row.get("trace_id"),
                    "result_type": "evaluated",
                    "error": row.get("error"),
                }
            )
    return rows


def _domain_from_scenario_id(scenario_id: str) -> str | None:
    if scenario_id.startswith("cs_"):
        return "customer_support"
    if scenario_id.startswith("dev_"):
        return "devops"
    if scenario_id.startswith("exp_"):
        return "workplace_expense"
    return None


def _summary_overall(summary: dict[str, Any]) -> dict[str, Any]:
    if "overall" in summary:
        return dict(summary["overall"])
    return {
        "attempted_scenarios": summary["total_scenarios"],
        "evaluated_scenarios": summary["total_scenarios"],
        "passed_scenarios": summary["passed_scenarios"],
        "failed_scenarios": summary["failed_scenarios"],
        "infrastructure_errors": 0,
        "pass_rate": summary["passed_scenarios"] / summary["total_scenarios"],
    }


def _scenario_outcome(summary: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    row = next(item for item in _result_rows(summary) if item["scenario_id"] == scenario_id)
    evaluated = row.get("result_type", "evaluated") == "evaluated" and row.get("error") is None
    action_distribution = {row.get("selected_action", "ERROR"): 1} if evaluated else {}
    return {
        "scenario_id": scenario_id,
        "selected_action": row.get("selected_action"),
        "expected_action": row.get("expected_action"),
        "passed": row.get("passed"),
        "repaired": bool(row.get("passed")),
        "action_distribution": action_distribution,
        "replay_stability": 1.0 if evaluated else 0.0,
        "supported_decision": bool(row.get("passed")),
        "infrastructure_errors": [] if evaluated else [row.get("error")],
        "trace_id": row.get("trace_id"),
        "needs_human_review": False,
        "action_changed": False,
    }


def _domain_slice(summary: dict[str, Any], domain: str) -> dict[str, Any]:
    rows = [row for row in _result_rows(summary) if row.get("domain") == domain]
    passed = sum(1 for row in rows if row.get("passed") is True)
    failed = sum(1 for row in rows if row.get("passed") is False)
    infra = sum(1 for row in rows if row.get("result_type") != "evaluated")
    return {
        "domain": domain,
        "attempted": len(rows),
        "evaluated": passed + failed,
        "passed": passed,
        "failed": failed,
        "infrastructure_errors": infra,
        "changed_scenarios": [row["scenario_id"] for row in rows],
    }


def _tool_call_changes(
    before_summary: dict[str, Any],
    after_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    before_rows = {row["scenario_id"]: row for row in _result_rows(before_summary)}
    after_rows = {row["scenario_id"]: row for row in _result_rows(after_summary)}
    changes: list[dict[str, Any]] = []
    for scenario_id in sorted(set(before_rows) & set(after_rows)):
        before_trace_id = before_rows[scenario_id].get("trace_id")
        after_trace_id = after_rows[scenario_id].get("trace_id")
        if before_trace_id == after_trace_id:
            continue
        changes.append(
            {
                "scenario_id": scenario_id,
                "before_trace_id": before_trace_id,
                "after_trace_id": after_trace_id,
            }
        )
    return changes


def _build_after_summary(
    cases: list[BenchmarkCase],
    traces: list[ExecutionTrace],
) -> dict[str, Any]:
    case_map = {case.scenario.id: case for case in cases}
    scenario_results: list[dict[str, Any]] = []
    results_by_domain: dict[str, dict[str, int]] = {}
    results_by_category: dict[str, dict[str, int]] = {}
    infrastructure_errors: list[dict[str, Any]] = []
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    latency = {"total_latency_ms": 0}
    passed = 0
    failed = 0
    evaluated = 0

    for trace in traces:
        case = case_map[trace.scenario_id]
        latency["total_latency_ms"] += trace.latency_ms
        for key, value in trace.token_usage.items():
            token_usage[key] = token_usage.get(key, 0) + value
        domain_bucket = results_by_domain.setdefault(
            case.scenario.domain.value,
            {"attempted": 0, "evaluated": 0, "passed": 0, "failed": 0, "infrastructure_errors": 0},
        )
        category_bucket = results_by_category.setdefault(
            case.scenario.failure_category,
            {"attempted": 0, "evaluated": 0, "passed": 0, "failed": 0, "infrastructure_errors": 0},
        )
        domain_bucket["attempted"] += 1
        category_bucket["attempted"] += 1

        if trace.error is not None or trace.passed is None or trace.selected_action is None:
            domain_bucket["infrastructure_errors"] += 1
            category_bucket["infrastructure_errors"] += 1
            infrastructure_errors.append(
                {
                    "scenario_id": trace.scenario_id,
                    "error": trace.error.model_dump(mode="json") if trace.error else None,
                }
            )
            scenario_results.append(
                {
                    "scenario_id": trace.scenario_id,
                    "domain": case.scenario.domain.value,
                    "failure_category": case.scenario.failure_category,
                    "trace_id": trace.trace_id,
                    "result_type": "infrastructure_error",
                    "expected_action": case.scenario.expected_action,
                    "actual_selected_action": trace.selected_action,
                    "passed": None,
                    "cache_status": trace.cache.hit,
                    "execution_source": trace.execution_source,
                    "latency_ms": trace.latency_ms,
                    "request_token_usage": trace.request_token_usage,
                    "cached_original_token_usage": trace.cached_original_token_usage,
                    "billable_api_call": trace.billable_api_call,
                    "error": trace.error.model_dump(mode="json") if trace.error else None,
                }
            )
            continue

        evaluated += 1
        domain_bucket["evaluated"] += 1
        category_bucket["evaluated"] += 1
        if trace.passed:
            passed += 1
            domain_bucket["passed"] += 1
            category_bucket["passed"] += 1
        else:
            failed += 1
            domain_bucket["failed"] += 1
            category_bucket["failed"] += 1
        scenario_results.append(
            {
                "scenario_id": trace.scenario_id,
                "domain": case.scenario.domain.value,
                "failure_category": case.scenario.failure_category,
                "trace_id": trace.trace_id,
                "result_type": "evaluated",
                "expected_action": case.scenario.expected_action,
                "actual_selected_action": trace.selected_action,
                "passed": trace.passed,
                "cache_status": trace.cache.hit,
                "execution_source": trace.execution_source,
                "latency_ms": trace.latency_ms,
                "request_token_usage": trace.request_token_usage,
                "cached_original_token_usage": trace.cached_original_token_usage,
                "billable_api_call": trace.billable_api_call,
                "error": None,
            }
        )

    return {
        "overall": {
            "attempted_scenarios": len(cases),
            "evaluated_scenarios": evaluated,
            "passed_scenarios": passed,
            "failed_scenarios": failed,
            "infrastructure_errors": len(infrastructure_errors),
            "pass_rate": (passed / evaluated) if evaluated else None,
        },
        "results_by_domain": results_by_domain,
        "results_by_failure_category": results_by_category,
        "scenario_results": scenario_results,
        "infrastructure_errors": infrastructure_errors,
        "totals": {
            "token_usage": token_usage,
            "latency": latency,
        },
    }
