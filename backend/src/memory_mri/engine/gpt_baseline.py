from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import BenchmarkCase, ExecutionTrace, ScenarioResult


@dataclass(frozen=True)
class GPTBaselineRunConfig:
    requested_model: str
    prompt_version: str
    timeout_seconds: float
    max_retries: int
    cache_enabled: bool
    reasoning_effort: str | None
    verbosity: str | None
    cache_dir: str


@dataclass(frozen=True)
class GPTBaselinePreflight:
    automated_checks_passed: bool
    requested_model: str
    prompt_version: str
    cache_enabled: bool
    git_commit_hash: str
    git_branch_state: str
    total_scenarios: int


class GPTBaselineService:
    def __init__(
        self,
        *,
        database_url: str,
        runner: OpenAIAgentRunner,
        data_dir: Path,
        git_commit_hash: str,
        git_branch_state: str,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.runner = runner
        self.data_dir = data_dir
        self.git_commit_hash = git_commit_hash
        self.git_branch_state = git_branch_state

    def preflight(self, *, automated_checks_passed: bool) -> GPTBaselinePreflight:
        cases = load_benchmark_cases(self.data_dir)
        return GPTBaselinePreflight(
            automated_checks_passed=automated_checks_passed,
            requested_model=self.runner.settings.model,
            prompt_version=self.runner.settings.prompt_version,
            cache_enabled=self.runner.settings.cache_enabled,
            git_commit_hash=self.git_commit_hash,
            git_branch_state=self.git_branch_state,
            total_scenarios=len(cases),
        )

    def run_official_baseline(
        self,
        *,
        summary_json_path: Path,
        summary_md_path: Path,
        traces_dir: Path,
    ) -> dict[str, Any]:
        cases = load_benchmark_cases(self.data_dir)
        if len(cases) != 30:
            raise ValueError(f"expected 30 scenarios, found {len(cases)}")

        traces_dir.mkdir(parents=True, exist_ok=True)
        for case in cases:
            self.repository.import_case(case)
        self.session.commit()

        attempted: list[dict[str, Any]] = []
        scenario_results: list[ScenarioResult] = []
        total_latency_ms = 0
        total_request_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        total_cached_original_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        total_billable_api_calls = 0

        for case in cases:
            trace = self._run_case(case)
            self.repository.save_trace(trace)
            self.session.commit()
            self._write_trace_artifact(traces_dir, trace)

            total_latency_ms += trace.latency_ms
            if trace.billable_api_call:
                total_billable_api_calls += 1
            _accumulate_tokens(total_request_tokens, trace.request_token_usage)
            _accumulate_tokens(total_cached_original_tokens, trace.cached_original_token_usage)

            attempted.append(_trace_summary_row(case, trace))
            if trace.passed is not None and trace.selected_action is not None:
                scenario_results.append(
                    ScenarioResult(
                        scenario_id=case.scenario.id,
                        selected_action=trace.selected_action,
                        expected_action=case.scenario.expected_action,
                        passed=trace.passed,
                        retrieved_memory_ids=trace.retrieved_memory_ids,
                        trace_id=trace.trace_id,
                        error=None,
                    )
                )

        summary = build_gpt_baseline_summary(
            cases=cases,
            traces=attempted,
            requested_model=self.runner.settings.model,
            prompt_version=self.runner.settings.prompt_version,
            run_config=GPTBaselineRunConfig(
                requested_model=self.runner.settings.model,
                prompt_version=self.runner.settings.prompt_version,
                timeout_seconds=self.runner.settings.timeout_seconds,
                max_retries=self.runner.settings.max_retries,
                cache_enabled=self.runner.settings.cache_enabled,
                reasoning_effort=self.runner.settings.reasoning_effort,
                verbosity=self.runner.settings.verbosity,
                cache_dir=str(self.runner.settings.cache_dir),
            ),
            git_commit_hash=self.git_commit_hash,
            git_branch_state=self.git_branch_state,
            timestamp=time_to_iso8601(datetime.now(timezone.utc)),
            total_latency_ms=total_latency_ms,
            total_request_tokens=total_request_tokens,
            total_cached_original_tokens=total_cached_original_tokens,
            total_billable_api_calls=total_billable_api_calls,
        )
        summary_json_path.parent.mkdir(parents=True, exist_ok=True)
        summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary_md_path.parent.mkdir(parents=True, exist_ok=True)
        summary_md_path.write_text(render_gpt_baseline_markdown(summary), encoding="utf-8")

        run_id = f"gpt_baseline_{uuid4().hex}"
        self.repository.save_benchmark_run(
            run_id=run_id,
            total_scenarios=len(cases),
            passed_scenarios=summary["overall"]["passed_scenarios"],
            payload=summary,
        )
        self.session.commit()
        summary["run_id"] = run_id
        return summary

    def _run_case(self, case: BenchmarkCase) -> ExecutionTrace:
        try:
            return self.runner.run_scenario(case.scenario, case.memories)
        except OpenAIRunnerError as exc:
            if exc.trace is None:
                raise
            return exc.trace

    def _write_trace_artifact(self, traces_dir: Path, trace: ExecutionTrace) -> None:
        trace_path = traces_dir / f"{trace.scenario_id}.json"
        trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")


def build_gpt_baseline_summary(
    *,
    cases: list[BenchmarkCase],
    traces: list[dict[str, Any]],
    requested_model: str,
    prompt_version: str,
    run_config: GPTBaselineRunConfig,
    git_commit_hash: str,
    git_branch_state: str,
    timestamp: str,
    total_latency_ms: int,
    total_request_tokens: dict[str, int],
    total_cached_original_tokens: dict[str, int],
    total_billable_api_calls: int,
) -> dict[str, Any]:
    cases_by_id = {case.scenario.id: case for case in cases}
    evaluated = [row for row in traces if row["result_type"] == "evaluated"]
    infra_errors = [row for row in traces if row["result_type"] == "infrastructure_error"]
    passed = [row for row in evaluated if row["passed"]]
    failed = [row for row in evaluated if not row["passed"]]

    by_domain = _summarize_group(
        keys=[case.scenario.domain.value for case in cases],
        rows=traces,
        key_fn=lambda row: row["domain"],
    )
    by_category = _summarize_group(
        keys=[case.scenario.failure_category for case in cases],
        rows=traces,
        key_fn=lambda row: row["failure_category"],
    )

    infrastructure_error_rows = [
        {
            "scenario_id": row["scenario_id"],
            "failure_category": row["failure_category"],
            "error": row["error"],
            "cache_status": row["cache_status"],
            "latency_ms": row["latency_ms"],
        }
        for row in infra_errors
    ]

    deep_dive_categories = [
        "contradictory-memories",
        "two-memory-interaction",
        "wrong-context-valid-memory",
    ]
    deep_dive_candidates: dict[str, dict[str, Any] | None] = {}
    for category in deep_dive_categories:
        candidate = next((row for row in failed if row["failure_category"] == category), None)
        deep_dive_candidates[category] = (
            None
            if candidate is None
            else {
                "scenario_id": candidate["scenario_id"],
                "expected_action": candidate["expected_action"],
                "actual_selected_action": candidate["actual_selected_action"],
            }
        )

    return {
        "model": requested_model,
        "prompt_versions": {
            domain: prompt_version
            for domain in sorted({case.scenario.domain.value for case in cases})
        },
        "run_configuration": asdict(run_config),
        "timestamp": timestamp,
        "git_commit_hash": git_commit_hash,
        "git_branch_state": git_branch_state,
        "overall": {
            "attempted_scenarios": len(traces),
            "evaluated_scenarios": len(evaluated),
            "passed_scenarios": len(passed),
            "failed_scenarios": len(failed),
            "infrastructure_errors": len(infra_errors),
            "pass_rate": (len(passed) / len(evaluated)) if evaluated else None,
        },
        "results_by_domain": by_domain,
        "results_by_failure_category": by_category,
        "failed_scenario_ids": [row["scenario_id"] for row in failed],
        "scenario_results": traces,
        "infrastructure_errors": infrastructure_error_rows,
        "totals": {
            "total_latency_ms": total_latency_ms,
            "request_token_usage": total_request_tokens,
            "cached_original_token_usage": total_cached_original_tokens,
            "billable_api_calls": total_billable_api_calls,
        },
        "deep_dive_candidates": deep_dive_candidates,
        "expected_action_changes": "none",
        "cases_loaded": len(cases_by_id),
    }


def render_gpt_baseline_markdown(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    lines = [
        "# GPT Baseline Summary",
        "",
        f"- Model: `{summary['model']}`",
        f"- Prompt version: `{next(iter(summary['prompt_versions'].values()))}`",
        f"- Timestamp: `{summary['timestamp']}`",
        f"- Git commit: `{summary['git_commit_hash']}`",
        f"- Cache enabled: `{summary['run_configuration']['cache_enabled']}`",
        f"- Attempted scenarios: `{overall['attempted_scenarios']}`",
        f"- Evaluated scenarios: `{overall['evaluated_scenarios']}`",
        f"- Passed: `{overall['passed_scenarios']}`",
        f"- Failed: `{overall['failed_scenarios']}`",
        f"- Infrastructure errors: `{overall['infrastructure_errors']}`",
        "",
        "## By Domain",
        "",
    ]
    for domain, bucket in summary["results_by_domain"].items():
        lines.append(
            f"- `{domain}`: attempted={bucket['attempted']} "
            f"evaluated={bucket['evaluated']} passed={bucket['passed']} "
            f"failed={bucket['failed']} infra_errors={bucket['infrastructure_errors']}"
        )
    lines.extend(["", "## By Failure Category", ""])
    for category, bucket in summary["results_by_failure_category"].items():
        lines.append(
            f"- `{category}`: attempted={bucket['attempted']} "
            f"evaluated={bucket['evaluated']} passed={bucket['passed']} "
            f"failed={bucket['failed']} infra_errors={bucket['infrastructure_errors']}"
        )
    lines.extend(["", "## Failed Scenarios", ""])
    if not summary["failed_scenario_ids"]:
        lines.append("- None")
    else:
        for row in summary["scenario_results"]:
            if row["result_type"] != "evaluated" or row["passed"]:
                continue
            lines.append(
                f"- `{row['scenario_id']}`: expected `{row['expected_action']}`, "
                f"actual `{row['actual_selected_action']}`, cache `{row['cache_status']}`"
            )
    lines.extend(["", "## Infrastructure Errors", ""])
    if not summary["infrastructure_errors"]:
        lines.append("- None")
    else:
        for row in summary["infrastructure_errors"]:
            lines.append(
                f"- `{row['scenario_id']}`: `{row['error']['code']}` - {row['error']['message']}"
            )
    lines.extend(["", "## Deep Dive Candidates", ""])
    for category, candidate in summary["deep_dive_candidates"].items():
        if candidate is None:
            lines.append(f"- `{category}`: no failure in this category")
        else:
            lines.append(
                f"- `{category}`: `{candidate['scenario_id']}` "
                f"(`{candidate['expected_action']}` -> `{candidate['actual_selected_action']}`)"
            )
    return "\n".join(lines) + "\n"


def _trace_summary_row(case: BenchmarkCase, trace: ExecutionTrace) -> dict[str, Any]:
    result_type = "evaluated" if trace.passed is not None else "infrastructure_error"
    return {
        "scenario_id": case.scenario.id,
        "domain": case.scenario.domain.value,
        "failure_category": case.scenario.failure_category,
        "trace_id": trace.trace_id,
        "result_type": result_type,
        "expected_action": case.scenario.expected_action,
        "actual_selected_action": trace.selected_action,
        "passed": trace.passed,
        "cache_status": trace.cache.hit,
        "execution_source": trace.execution_source,
        "latency_ms": trace.latency_ms,
        "request_token_usage": trace.request_token_usage,
        "cached_original_token_usage": trace.cached_original_token_usage,
        "billable_api_call": trace.billable_api_call,
        "error": trace.error.model_dump(mode="json") if trace.error is not None else None,
    }


def _summarize_group(
    *,
    keys: list[str],
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for key in sorted(set(keys)):
        summary[key] = {
            "attempted": 0,
            "evaluated": 0,
            "passed": 0,
            "failed": 0,
            "infrastructure_errors": 0,
        }
    for row in rows:
        bucket = summary[key_fn(row)]
        bucket["attempted"] += 1
        if row["result_type"] == "infrastructure_error":
            bucket["infrastructure_errors"] += 1
            continue
        bucket["evaluated"] += 1
        bucket["passed" if row["passed"] else "failed"] += 1
    return summary


def _accumulate_tokens(target: dict[str, int], usage: dict[str, int] | None) -> None:
    if usage is None:
        return
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        target[key] += usage.get(key, 0)


def time_to_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
