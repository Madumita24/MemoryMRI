from __future__ import annotations

import json
from pathlib import Path

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings
from memory_mri.engine.benchmark import BenchmarkService
from memory_mri.engine.repair_proposals import RepairProposalEngine
from memory_mri.engine.verification import VerificationEngine
from memory_mri.schemas import TraceErrorDetails, VerificationVerdict
from tests.test_repair_proposals import FakeClient, copy_investigation, draft_response, seed_trace

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = ROOT / "artifacts" / "investigations"
BENCHMARK_ROOT = ROOT / "benchmark" / "data"


def make_settings(tmp_path: Path) -> OpenAISettings:
    return OpenAISettings(
        api_key="test-key",
        model="gpt-5.6",
        timeout_seconds=5.0,
        max_retries=0,
        cache_enabled=False,
        prompt_version="v1",
        reasoning_effort=None,
        verbosity="low",
        cache_dir=tmp_path / "openai-cache",
    )


def make_proposal_engine(
    tmp_path: Path,
    *,
    database_url: str,
    client: FakeClient | None,
) -> RepairProposalEngine:
    return RepairProposalEngine(
        database_url=database_url,
        data_dir=BENCHMARK_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1", "v1"),
        client=client,
    )


def make_verification_engine(
    tmp_path: Path,
    *,
    database_url: str,
    fake_baseline_path: Path,
) -> VerificationEngine:
    return VerificationEngine(
        database_url=database_url,
        data_dir=BENCHMARK_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        fake_baseline_path=fake_baseline_path,
        gpt_baseline_path=tmp_path / "artifacts" / "gpt-baseline-summary.json",
        openai_settings=make_settings(tmp_path),
    )


def write_custom_fake_baseline(
    tmp_path: Path,
    *,
    name: str = "fake-baseline.json",
    override_failures: set[str] | None = None,
    override_passes: set[str] | None = None,
) -> Path:
    override_failures = override_failures or set()
    override_passes = override_passes or set()
    database_url = f"sqlite:///{tmp_path / 'baseline.db'}"
    service = BenchmarkService(
        database_url=database_url,
        runner=FakeAgentRunner(),
        data_dir=BENCHMARK_ROOT,
    )
    baseline_path = tmp_path / "artifacts" / name
    summary = service.run_baseline(baseline_path)
    cases = {case.scenario.id: case for case in load_benchmark_cases(BENCHMARK_ROOT)}

    for row in summary["scenario_results"]:
        case = cases[row["scenario_id"]]
        if row["scenario_id"] in override_failures:
            row["selected_action"] = case.scenario.allowed_actions[0]
            if row["selected_action"] == case.scenario.expected_action:
                row["selected_action"] = case.scenario.allowed_actions[-1]
            row["passed"] = False
        elif row["scenario_id"] in override_passes:
            row["selected_action"] = case.scenario.expected_action
            row["passed"] = True

    summary["passed_scenarios"] = sum(1 for row in summary["scenario_results"] if row["passed"])
    summary["failed_scenarios"] = summary["total_scenarios"] - summary["passed_scenarios"]
    for bucket in summary["results_by_domain"].values():
        bucket["passed"] = 0
        bucket["failed"] = 0
    for bucket in summary["results_by_failure_category"].values():
        bucket["passed"] = 0
        bucket["failed"] = 0
    for row in summary["scenario_results"]:
        case = cases[row["scenario_id"]]
        domain_bucket = summary["results_by_domain"][case.scenario.domain.value]
        domain_bucket["passed" if row["passed"] else "failed"] += 1
        category_bucket = summary["results_by_failure_category"][case.scenario.failure_category]
        category_bucket["passed" if row["passed"] else "failed"] += 1

    baseline_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return baseline_path


def prepare_applied_cs01(tmp_path: Path, benchmark_cases) -> tuple[str, str]:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    engine = make_proposal_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient(
            [
                draft_response(
                    repair_type="REQUIRE_HUMAN_CONFIRMATION",
                    target_memory_ids=["cs_01_mem_2"],
                )
            ]
        ),
    )
    proposal = engine.generate_proposal(investigation_id)
    engine.approve_proposal(proposal.proposal_id, approval_reason="Reviewed.")
    engine.apply_proposal(proposal.proposal_id)
    return database_url, proposal.proposal_id


def test_verify_original_marks_cs01_as_unsupported_behavior_change(
    benchmark_cases,
    tmp_path: Path,
) -> None:
    database_url, proposal_id = prepare_applied_cs01(tmp_path, benchmark_cases)
    baseline_path = write_custom_fake_baseline(tmp_path, override_failures={"cs_01"})
    engine = make_verification_engine(
        tmp_path,
        database_url=database_url,
        fake_baseline_path=baseline_path,
    )

    verification = engine.verify_original(proposal_id, runner_name="fake")

    assert verification.original_case_before["passed"] is False
    assert verification.original_case_after["passed"] is True
    assert verification.repaired_failures == ["cs_01"]
    assert verification.verdict == VerificationVerdict.UNSUPPORTED_BEHAVIOR_CHANGE


def test_verify_domain_surfaces_repair_and_regression(benchmark_cases, tmp_path: Path) -> None:
    database_url, proposal_id = prepare_applied_cs01(tmp_path, benchmark_cases)
    baseline_path = write_custom_fake_baseline(
        tmp_path,
        name="domain-before.json",
        override_failures={"cs_01"},
        override_passes={"cs_02"},
    )
    baseline_before = baseline_path.read_text(encoding="utf-8")
    engine = make_verification_engine(
        tmp_path,
        database_url=database_url,
        fake_baseline_path=baseline_path,
    )

    verification = engine.verify_domain(proposal_id, runner_name="fake")

    assert "cs_01" in verification.repaired_failures
    assert "cs_02" in verification.new_regressions
    assert baseline_path.read_text(encoding="utf-8") == baseline_before


def test_verify_full_benchmark_excludes_infrastructure_errors(
    benchmark_cases,
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url, proposal_id = prepare_applied_cs01(tmp_path, benchmark_cases)
    baseline_path = write_custom_fake_baseline(
        tmp_path,
        name="full-before.json",
        override_failures={"cs_01"},
    )
    engine = make_verification_engine(
        tmp_path,
        database_url=database_url,
        fake_baseline_path=baseline_path,
    )

    class ErrorRunner(FakeAgentRunner):
        def run_scenario(self, scenario, memories):
            trace = super().run_scenario(scenario, memories)
            if scenario.id == "dev_01":
                trace.selected_action = None
                trace.structured_response = None
                trace.passed = None
                trace.evaluation.evaluator_result = None
                trace.error = TraceErrorDetails(
                    code="network",
                    message="network",
                    retryable=True,
                    attempts=1,
                )
            return trace

    monkeypatch.setattr(engine, "_runner", lambda runner_name: ErrorRunner())
    verification = engine.verify_full_benchmark(proposal_id, runner_name="fake")

    assert verification.full_after["attempted_scenarios"] == 30
    assert verification.full_after["evaluated_scenarios"] == 29
    assert verification.infrastructure_errors


def test_no_repair_proposal_is_not_applicable(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "exp_09")
    investigation_id = "inv_ff4ed6ca0666440a85a758168e5ca9b4"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_0f0477f7cb5c497cb209414fce5e1016",
        selected_action="REQUEST_DOCUMENTATION",
    )
    proposal_engine = make_proposal_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient([]),
    )
    proposal = proposal_engine.generate_proposal(investigation_id)
    baseline_path = write_custom_fake_baseline(tmp_path, override_failures={"exp_09"})
    engine = make_verification_engine(
        tmp_path,
        database_url=database_url,
        fake_baseline_path=baseline_path,
    )

    verification = engine.verify_original(proposal.proposal_id, runner_name="fake")

    assert verification.verdict == VerificationVerdict.MEMORY_REPAIR_NOT_APPLICABLE
    assert verification.after_benchmark_id == "not-applicable"


def test_compare_benchmarks_reports_changes(tmp_path: Path) -> None:
    before_path = write_custom_fake_baseline(
        tmp_path,
        name="compare-before.json",
        override_failures={"cs_01"},
    )
    after_path = write_custom_fake_baseline(
        tmp_path,
        name="compare-after.json",
        override_passes={"cs_01", "cs_02"},
    )
    engine = make_verification_engine(
        tmp_path,
        database_url=f"sqlite:///{tmp_path / 'compare.db'}",
        fake_baseline_path=before_path,
    )

    comparison = engine.compare_benchmarks(before_path, after_path)

    assert "cs_01" in comparison["repaired_failures"]
    assert comparison["action_changes"]


def test_verification_uses_applied_memory_snapshot(benchmark_cases, tmp_path: Path) -> None:
    database_url, proposal_id = prepare_applied_cs01(tmp_path, benchmark_cases)
    baseline_path = write_custom_fake_baseline(tmp_path, override_failures={"cs_01"})
    engine = make_verification_engine(
        tmp_path,
        database_url=database_url,
        fake_baseline_path=baseline_path,
    )

    verification = engine.verify_original(proposal_id, runner_name="fake")
    traces = engine.repository.list_traces_for_scenario("cs_01")
    latest = traces[-1]

    assert verification.original_case_after["trace_id"] == latest.trace_id
    assert any(
        memory.operational_metadata.get("requires_human_confirmation") is True
        for memory in latest.memory_snapshot
        if memory.memory_id == "cs_01_mem_2"
    )
