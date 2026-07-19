from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.analysis.models import (
    ContradictionAnalysisInput,
    SemanticMemoryAnalysis,
    SemanticPairAnalysis,
    SemanticPairAnalysisResponse,
    SuspicionAnalysisInput,
    SuspicionIssueType,
)
from memory_mri.analysis.semantic import SemanticAnalysisResult
from memory_mri.api import create_app
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.repair_proposals import RepairProposalEngine
from memory_mri.engine.verification import VerificationEngine
from memory_mri.engine.verification_artifacts import VerificationArtifactEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    ExecutionTrace,
    StructuredAgentResponse,
    TraceCacheStatus,
    TraceEvaluation,
    new_run_id,
    new_trace_id,
)
from tests.test_repair_proposals import FakeClient, copy_investigation, draft_response, seed_trace
from tests.test_verification import make_settings, write_custom_fake_baseline


@dataclass
class StubSemanticAnalyzer:
    def analyze_memory_suspicion(self, payload: SuspicionAnalysisInput) -> SemanticAnalysisResult:
        analyses = [
            SemanticMemoryAnalysis(
                memory_id=memory.memory_id,
                semantic_suspicion_score=0.9 if index == 0 else 0.2,
                suspected_issue_types=(
                    [SuspicionIssueType.STALE] if index == 0 else [SuspicionIssueType.NONE]
                ),
                concise_reason="Stub suspicion analysis",
                related_memory_ids=[],
                uncertainty=0.1,
                requires_human_review=False,
            )
            for index, memory in enumerate(payload.memories)
        ]
        return SemanticAnalysisResult(
            analyses=analyses,
            usage={},
            response_model="stub-model",
            prompt_hash="stub-prompt",
            request_hash="stub-request",
            cache_hit=False,
        )

    def analyze_pair_relationships(
        self, payload: ContradictionAnalysisInput
    ) -> SemanticAnalysisResult:
        pairs = [
            SemanticPairAnalysis(
                memory_a_id=pair.memory_a_id,
                memory_b_id=pair.memory_b_id,
                relationship="potentially_consistent",
                concise_explanation="Stub pair analysis",
                confidence=0.7,
                requires_human_review=False,
            )
            for pair in payload.pairs
        ]
        validated = SemanticPairAnalysisResponse(pairs=pairs)
        return SemanticAnalysisResult(
            analyses=validated.pairs,
            usage={},
            response_model="stub-model",
            prompt_hash="stub-prompt",
            request_hash="stub-request",
            cache_hit=False,
        )


def make_failed_trace(case) -> ExecutionTrace:
    agent_input = case.scenario.to_agent_input(case.memories)
    memory_snapshot = [memory.to_agent_input() for memory in case.memories]
    selected_action = case.scenario.allowed_actions[-1]
    return ExecutionTrace(
        trace_id=new_trace_id(),
        scenario_id=case.scenario.id,
        run_id=new_run_id(),
        domain=case.scenario.domain,
        user_input=case.scenario.user_input,
        agent_input=agent_input,
        requested_model="fake-deterministic",
        response_model="fake-deterministic",
        model="fake-deterministic",
        prompt_version="day2h-test",
        retrieved_memory_ids=[memory.id for memory in case.memories],
        memory_snapshot=memory_snapshot,
        structured_response=StructuredAgentResponse(
            selected_action=selected_action,
            action_arguments={},
            cited_memory_ids=[memory.memory_id for memory in memory_snapshot[:2]],
            concise_rationale="Seeded failed trace",
            uncertainty=0.5,
            needs_human_review=False,
        ),
        selected_action=selected_action,
        action_arguments={},
        cited_memory_ids=[memory.memory_id for memory in memory_snapshot[:2]],
        concise_rationale="Seeded failed trace",
        uncertainty=0.5,
        needs_human_review=False,
        evaluation=TraceEvaluation(evaluator_result=None),
        passed=False,
        execution_source="deterministic",
        cache_lookup_latency_ms=None,
        original_model_latency_ms=None,
        latency_ms=1,
        token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        request_token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        cached_original_token_usage=None,
        billable_api_call=False,
        cache=TraceCacheStatus(enabled=False, hit=False),
        created_at=datetime.now(timezone.utc),
    )


def build_test_client(tmp_path: Path, benchmark_cases) -> tuple[TestClient, str]:
    case = next(item for item in benchmark_cases if item.scenario.id == "cs_01").model_copy(
        deep=True
    )
    database_url = f"sqlite:///{tmp_path / 'memory.db'}"
    session = create_sqlite_session(database_url)
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    failed_trace = make_failed_trace(case)
    repository.save_trace(failed_trace)
    session.commit()

    def analysis_engine_factory() -> InvestigationAnalysisEngine:
        return InvestigationAnalysisEngine(
            database_url=database_url,
            artifacts_dir=tmp_path / "artifacts",
            settings=OpenAISettings(
                api_key="test-key",
                model="gpt-5.6",
                timeout_seconds=5.0,
                max_retries=0,
                cache_enabled=False,
                prompt_version="v1",
                reasoning_effort=None,
                verbosity="low",
                cache_dir=tmp_path / "cache",
            ),
            prompt_settings=SemanticAnalysisSettings(
                suspicion_prompt_version="v1",
                contradiction_prompt_version="v1",
            ),
            semantic_analyzer=StubSemanticAnalyzer(),
        )

    def proposal_engine_factory() -> RepairProposalEngine:
        return RepairProposalEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
            settings=make_settings(tmp_path),
            prompt_settings=SemanticAnalysisSettings(
                suspicion_prompt_version="v1",
                contradiction_prompt_version="v1",
                repair_prompt_version="v1",
            ),
            client=FakeClient(
                [
                    draft_response(
                        repair_type="REQUIRE_HUMAN_CONFIRMATION",
                        target_memory_ids=["cs_01_mem_2"],
                    )
                ]
            ),
            analysis_engine=analysis_engine_factory(),
        )

    def verification_engine_factory() -> VerificationEngine:
        return VerificationEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
            fake_baseline_path=write_custom_fake_baseline(
                tmp_path,
                name="api-before.json",
                override_failures={"cs_01"},
            ),
            gpt_baseline_path=tmp_path / "artifacts" / "api-gpt-before.json",
            openai_settings=make_settings(tmp_path),
        )

    def artifact_engine_factory() -> VerificationArtifactEngine:
        return VerificationArtifactEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
        )

    app = create_app(
        database_url=database_url,
        data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
        artifacts_dir=tmp_path / "artifacts",
        analysis_engine_factory=analysis_engine_factory,
        proposal_engine_factory=proposal_engine_factory,
        verification_engine_factory=verification_engine_factory,
        artifact_engine_factory=artifact_engine_factory,
    )
    return TestClient(app), failed_trace.trace_id


def test_scenario_endpoints_hide_answer_key_fields(tmp_path: Path, benchmark_cases) -> None:
    client, _ = build_test_client(tmp_path, benchmark_cases)

    list_response = client.get("/scenarios")
    assert list_response.status_code == 200
    assert "expected_action" not in list_response.text
    assert "failure_category" not in list_response.text

    detail_response = client.get("/scenarios/cs_01")
    assert detail_response.status_code == 200
    assert "expected_action" not in detail_response.text
    assert "expected_problematic_memory_ids" not in detail_response.text
    assert "evaluator_config" not in detail_response.text
    assert detail_response.json()["agent_input"]["scenario_id"] == "cs_01"


def test_run_trace_and_trace_listing_endpoints(tmp_path: Path, benchmark_cases) -> None:
    client, _ = build_test_client(tmp_path, benchmark_cases)

    run_response = client.post("/runs", json={"scenario_id": "cs_01", "runner": "fake"})
    assert run_response.status_code == 200
    trace_id = run_response.json()["trace_id"]
    assert "evaluation" not in run_response.text

    trace_response = client.get(f"/traces/{trace_id}")
    assert trace_response.status_code == 200
    assert trace_response.json()["scenario_id"] == "cs_01"

    list_response = client.get("/scenarios/cs_01/traces")
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 1


def test_investigation_endpoints_and_results(tmp_path: Path, benchmark_cases) -> None:
    client, trace_id = build_test_client(tmp_path, benchmark_cases)

    investigation_response = client.post(
        "/investigations",
        json={"trace_id": trace_id, "mode": "fast"},
    )
    assert investigation_response.status_code == 200
    investigation_id = investigation_response.json()["investigation_id"]
    assert "expected_action" not in investigation_response.text

    replay_response = client.post(
        f"/investigations/{investigation_id}/individual-replay",
        json={"operation": "all"},
    )
    assert replay_response.status_code == 200
    assert replay_response.json()["replay_results"]

    suspicion_response = client.post(
        f"/investigations/{investigation_id}/suspicion-ranking",
        json={},
    )
    assert suspicion_response.status_code == 200
    assert suspicion_response.json()["metadata"]["investigation_id"] == investigation_id

    contradictions_response = client.post(
        f"/investigations/{investigation_id}/contradictions",
        json={},
    )
    assert contradictions_response.status_code == 200
    assert contradictions_response.json()["metadata"]["investigation_id"] == investigation_id

    pairwise_response = client.post(
        f"/investigations/{investigation_id}/pairwise-replay",
        json={"all_pairs": True},
    )
    assert pairwise_response.status_code == 200
    assert pairwise_response.json()["pair_results"]

    results_response = client.get(f"/investigations/{investigation_id}/results")
    assert results_response.status_code == 200
    payload = results_response.json()
    assert payload["investigation"]["investigation_id"] == investigation_id
    assert payload["suspicion_ranking"] is not None
    assert payload["contradictions"] is not None
    assert payload["pairwise_replay"] is not None


def test_api_errors_and_cache_clear(tmp_path: Path, benchmark_cases) -> None:
    client, _ = build_test_client(tmp_path, benchmark_cases)

    assert client.get("/scenarios/unknown").status_code == 404
    assert client.get("/traces/unknown").status_code == 404
    assert (
        client.post("/runs", json={"scenario_id": "unknown", "runner": "fake"}).status_code == 404
    )
    assert (
        client.post("/cache/clear", json={"mode": "scenario", "scenario_id": "unknown"}).status_code
        == 404
    )
    cache_response = client.post("/cache/clear", json={"mode": "all"})
    assert cache_response.status_code == 200
    assert cache_response.json()["mode"] == "all"


def test_proposal_verification_and_artifact_endpoints(tmp_path: Path, benchmark_cases) -> None:
    client, trace_id = build_test_client(tmp_path, benchmark_cases)
    investigation_response = client.post(
        "/investigations",
        json={"trace_id": trace_id, "mode": "fast"},
    )
    investigation_id = investigation_response.json()["investigation_id"]

    replay_response = client.post(
        f"/investigations/{investigation_id}/individual-replay",
        json={"operation": "all"},
    )
    assert replay_response.status_code == 200

    contradictions_response = client.post(
        f"/investigations/{investigation_id}/contradictions",
        json={},
    )
    assert contradictions_response.status_code == 200

    proposal_response = client.post(f"/investigations/{investigation_id}/proposals")
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal_id"]

    apply_before_approval = client.post(f"/proposals/{proposal_id}/apply")
    assert apply_before_approval.status_code == 400

    approve_response = client.post(
        f"/proposals/{proposal_id}/approve",
        json={"reason": "Reviewed evidence."},
    )
    assert approve_response.status_code == 200

    apply_response = client.post(f"/proposals/{proposal_id}/apply")
    assert apply_response.status_code == 200

    diff_response = client.get(f"/proposals/{proposal_id}/diff")
    assert diff_response.status_code == 200
    assert diff_response.json()["diff_id"].startswith("diff_")

    original_verification = client.post(
        "/verifications/original",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    assert original_verification.status_code == 200
    verification_id = original_verification.json()["verification_id"]

    domain_verification = client.post(
        "/verifications/domain",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    assert domain_verification.status_code == 200

    full_verification = client.post(
        "/verifications/full",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    assert full_verification.status_code == 200

    verification_detail = client.get(f"/verifications/{verification_id}")
    assert verification_detail.status_code == 200

    artifact_response = client.post("/artifacts", json={"proposal_id": proposal_id})
    assert artifact_response.status_code == 200
    artifact_id = artifact_response.json()["artifact_id"]
    first_certificate = artifact_response.json()["certificate_id"]

    second_artifact_response = client.post("/artifacts", json={"proposal_id": proposal_id})
    assert second_artifact_response.status_code == 200
    assert second_artifact_response.json()["certificate_id"] == first_certificate

    artifact_detail = client.get(f"/artifacts/{artifact_id}")
    assert artifact_detail.status_code == 200
    assert artifact_detail.json()["content_hash"] == first_certificate

    artifact_json = client.get(f"/artifacts/{artifact_id}/json")
    assert artifact_json.status_code == 200

    artifact_markdown = client.get(f"/artifacts/{artifact_id}/markdown")
    assert artifact_markdown.status_code == 200
    assert "Artifact Fingerprint" in artifact_markdown.text

    benchmark_response = client.post("/benchmarks/run", json={"runner": "fake"})
    assert benchmark_response.status_code == 200
    run_id = benchmark_response.json()["run_id"]
    assert run_id is not None
    benchmark_detail = client.get(f"/benchmarks/{run_id}")
    assert benchmark_detail.status_code == 200


def test_no_repair_api_flow_and_privacy(tmp_path: Path, benchmark_cases) -> None:
    case = next(item for item in benchmark_cases if item.scenario.id == "exp_09")
    investigation_id = "inv_ff4ed6ca0666440a85a758168e5ca9b4"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_0f0477f7cb5c497cb209414fce5e1016",
        selected_action="REQUEST_DOCUMENTATION",
    )

    def analysis_engine_factory() -> InvestigationAnalysisEngine:
        return InvestigationAnalysisEngine(
            database_url=database_url,
            artifacts_dir=tmp_path / "artifacts",
            settings=make_settings(tmp_path),
            prompt_settings=SemanticAnalysisSettings("v1", "v1", "v1"),
            semantic_analyzer=StubSemanticAnalyzer(),
        )

    def proposal_engine_factory() -> RepairProposalEngine:
        return RepairProposalEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
            settings=make_settings(tmp_path),
            prompt_settings=SemanticAnalysisSettings("v1", "v1", "v1"),
            client=FakeClient([]),
            analysis_engine=analysis_engine_factory(),
        )

    def verification_engine_factory() -> VerificationEngine:
        return VerificationEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
            fake_baseline_path=write_custom_fake_baseline(
                tmp_path,
                name="exp-before.json",
                override_failures={"exp_09"},
            ),
            gpt_baseline_path=tmp_path / "artifacts" / "exp-gpt-before.json",
            openai_settings=make_settings(tmp_path),
        )

    app = create_app(
        database_url=database_url,
        data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
        artifacts_dir=tmp_path / "artifacts",
        analysis_engine_factory=analysis_engine_factory,
        proposal_engine_factory=proposal_engine_factory,
        verification_engine_factory=verification_engine_factory,
        artifact_engine_factory=lambda: VerificationArtifactEngine(
            database_url=database_url,
            data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    client = TestClient(app)

    proposal_response = client.post(f"/investigations/{investigation_id}/proposals")
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal_id"]
    assert proposal_response.json()["repair_type"] == "ESCALATE_PROMPT_OR_POLICY_REVIEW"

    verify_response = client.post(
        "/verifications/original",
        json={"proposal_id": proposal_id, "runner": "fake"},
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["verdict"] == "MEMORY_REPAIR_NOT_APPLICABLE"

    artifact_response = client.post("/artifacts", json={"proposal_id": proposal_id})
    assert artifact_response.status_code == 200
    artifact_id = artifact_response.json()["artifact_id"]
    markdown_response = client.get(f"/artifacts/{artifact_id}/markdown")
    assert markdown_response.status_code == 200
    assert (
        "No memory changes proposed." in markdown_response.text
        or "prompt or policy" in markdown_response.text.lower()
    )
