from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.repair_proposals import RepairProposalEngine, RepairProposalError
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import RepairStatus, RepairType

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = ROOT / "artifacts" / "investigations"
BENCHMARK_ROOT = ROOT / "benchmark" / "data"


@dataclass
class FakeUsage:
    input_tokens: int = 50
    output_tokens: int = 25
    total_tokens: int = 75

    def model_dump(self, mode: str = "json") -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class FakeParsedResponse:
    output_text: str
    usage: FakeUsage | None = None
    id: str = "resp_repair"
    model: str = "gpt-5.6-sol"


class FakeResponsesAPI:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeParsedResponse:
        self.calls.append(kwargs)
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = FakeResponsesAPI(responses)


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


def copy_investigation(tmp_path: Path, investigation_id: str) -> Path:
    target = tmp_path / "artifacts" / "investigations" / investigation_id
    shutil.copytree(ARTIFACTS_ROOT / investigation_id, target)
    return target


def seed_trace(tmp_path: Path, case, *, trace_id: str, selected_action: str) -> str:
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    trace.trace_id = trace_id
    trace.requested_model = "gpt-5.6"
    trace.response_model = "gpt-5.6-sol"
    trace.model = "gpt-5.6-sol"
    trace.prompt_version = "v1"
    trace.prompt_content_hash = "prompt-hash"
    trace.selected_action = selected_action
    trace.concise_rationale = "Seeded failed trace."
    trace.passed = False
    if trace.structured_response is not None:
        trace.structured_response.selected_action = selected_action
        trace.structured_response.concise_rationale = "Seeded failed trace."
    if trace.evaluation.evaluator_result is not None:
        trace.evaluation.evaluator_result.selected_action = selected_action
        trace.evaluation.evaluator_result.passed = False
        trace.evaluation.evaluator_result.reason = "seeded failure"
    repository.save_trace(trace)
    session.commit()
    return f"sqlite:///{tmp_path / 'memory.db'}"


def make_engine(
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


def draft_response(
    *,
    repair_type: str,
    target_memory_ids: list[str],
) -> FakeParsedResponse:
    payload = {
        "repair_type": repair_type,
        "target_memory_ids": target_memory_ids,
        "proposed_after_state": [
            {"field_name": "metadata_update", "new_value": repair_type.lower()}
        ],
        "expected_affected_scenarios": ["cs_01"],
        "expected_behavior_change": (
            "Reduce stale-policy dominance and require a safer evidence check."
        ),
        "risks": [
            "Loss of valid historical information.",
            "Broader behavior changes in nearby refund scenarios.",
            "Unsupported expected action could still remain if policy interpretation is wrong.",
        ],
        "rollback_plan": "Revert the metadata-only change if neighboring scenarios regress.",
        "concise_explanation": (
            "Replay shows influence, but the changed outcome is not yet a supported repair."
        ),
        "confidence": 0.62,
        "requires_human_approval": True,
    }
    return FakeParsedResponse(output_text=json.dumps(payload), usage=FakeUsage())


def test_exp_09_returns_prompt_or_policy_escalation_without_gpt(
    benchmark_cases, tmp_path: Path
) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "exp_09")
    investigation_id = "inv_ff4ed6ca0666440a85a758168e5ca9b4"
    investigation_dir = copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_0f0477f7cb5c497cb209414fce5e1016",
        selected_action="REQUEST_DOCUMENTATION",
    )
    client = FakeClient([])
    engine = make_engine(tmp_path, database_url=database_url, client=client)

    proposal = engine.generate_proposal(investigation_id)

    assert proposal.repair_type == RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW
    assert proposal.target_memory_ids == []
    assert proposal.requires_human_approval is True
    assert proposal.model == "deterministic-evidence-gate"
    assert not client.responses.calls
    assert (investigation_dir / "repair-proposals" / f"{proposal.proposal_id}.json").exists()


def test_cs_01_generates_cautious_non_destructive_proposal(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    client = FakeClient(
        [
            draft_response(
                repair_type="ADD_PRECEDENCE_METADATA",
                target_memory_ids=["cs_01_mem_1", "cs_01_mem_2"],
            )
        ]
    )
    engine = make_engine(tmp_path, database_url=database_url, client=client)

    proposal = engine.generate_proposal(investigation_id)

    assert proposal.repair_type == RepairType.ADD_PRECEDENCE_METADATA
    assert proposal.target_memory_ids == ["cs_01_mem_1", "cs_01_mem_2"]
    assert proposal.requires_human_approval is True
    assert proposal.proposal_status == RepairStatus.PROPOSED
    assert proposal.repair_type not in {
        RepairType.INVALIDATE_MEMORY,
        RepairType.REPLACE_WITH_CORRECTED_FACT,
    }
    assert proposal.support_validity_result.decision_still_supported is False


def test_invalid_repair_type_is_rejected_for_cs_01(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    engine = make_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient(
            [draft_response(repair_type="INVALIDATE_MEMORY", target_memory_ids=["cs_01_mem_2"])]
        ),
    )

    with pytest.raises(RepairProposalError) as exc_info:
        engine.generate_proposal(investigation_id)

    assert exc_info.value.failure.code == "invalid_repair_type"


def test_unknown_target_memory_is_rejected(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    engine = make_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient(
            [
                draft_response(
                    repair_type="ADD_CONTEXT_CONSTRAINT",
                    target_memory_ids=["missing_memory"],
                )
            ]
        ),
    )

    with pytest.raises(RepairProposalError) as exc_info:
        engine.generate_proposal(investigation_id)

    assert exc_info.value.failure.code == "invalid_target_memory_ids"


def test_malformed_gpt_proposal_is_rejected(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    engine = make_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient(
            [FakeParsedResponse(output_text=json.dumps({"repair_type": "ADD_CONTEXT_CONSTRAINT"}))]
        ),
    )

    with pytest.raises(RepairProposalError) as exc_info:
        engine.generate_proposal(investigation_id)

    assert exc_info.value.failure.code == "invalid_model_output"


def test_proposal_request_hides_benchmark_private_fields(benchmark_cases, tmp_path: Path) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01").model_copy(
        deep=True
    )
    case.scenario.expected_problematic_memory_ids = ["SENTINEL_PROBLEMATIC_MEMORY"]
    case.scenario.failure_category = "SENTINEL_FAILURE_CATEGORY"
    case.scenario.explanation = "SENTINEL_EXPLANATION"
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    client = FakeClient(
        [
            draft_response(
                repair_type="REQUIRE_HUMAN_CONFIRMATION",
                target_memory_ids=["cs_01_mem_2"],
            )
        ]
    )
    engine = make_engine(tmp_path, database_url=database_url, client=client)

    engine.generate_proposal(investigation_id)

    request_text = client.responses.calls[0]["input"][0]["content"][0]["text"]
    combined = f"{client.responses.calls[0]['instructions']}\n{request_text}"
    assert "SENTINEL_PROBLEMATIC_MEMORY" not in combined
    assert "SENTINEL_FAILURE_CATEGORY" not in combined
    assert "SENTINEL_EXPLANATION" not in combined
    assert "expected_problematic_memory_ids" not in combined
    assert "failure_category" not in combined


def test_proposal_persistence_and_artifact_references_are_valid(
    benchmark_cases, tmp_path: Path
) -> None:
    case = next(case for case in benchmark_cases if case.scenario.id == "cs_01")
    investigation_id = "inv_6d6c10d634c140f3af029a3eb7826bde"
    investigation_dir = copy_investigation(tmp_path, investigation_id)
    database_url = seed_trace(
        tmp_path,
        case,
        trace_id="trace_6e225da6d76a4ae0b76ec0ee5c11fc5c",
        selected_action="ASK_FOR_INFORMATION",
    )
    engine = make_engine(
        tmp_path,
        database_url=database_url,
        client=FakeClient(
            [
                draft_response(
                    repair_type="ADD_CONTEXT_CONSTRAINT",
                    target_memory_ids=["cs_01_mem_2"],
                )
            ]
        ),
    )

    proposal = engine.generate_proposal(investigation_id)
    stored = engine.get_proposal(proposal.proposal_id)
    listed = engine.list_proposals(investigation_id)

    assert stored.proposal_id == proposal.proposal_id
    assert [item.proposal_id for item in listed] == [proposal.proposal_id]
    for artifact_name in proposal.evidence_references.replay_artifact_ids:
        assert (investigation_dir / artifact_name).exists()
    for artifact_name in proposal.evidence_references.contradiction_artifact_ids:
        assert (investigation_dir / artifact_name).exists()
    export_paths = engine.export_proposal(proposal.proposal_id)
    assert Path(export_paths["proposal_json"]).exists()
    assert Path(export_paths["proposal_markdown"]).exists()
