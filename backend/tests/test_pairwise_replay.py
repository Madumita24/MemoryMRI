from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from memory_mri.agents.base import AgentRunner
from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIActionSelection, OpenAIAgentRunner
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.evaluation import evaluate_action
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    ExecutionTrace,
    Intervention,
    InterventionType,
    MemoryControlType,
    MemoryDependenceClassification,
    PairEvidenceClassification,
    ReplayMode,
    ReplayResult,
    StructuredAgentResponse,
    TraceCacheStatus,
    TraceEvaluation,
    new_run_id,
    new_trace_id,
)


@dataclass
class FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 5
    total_tokens: int = 15

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
    id: str = "resp_pairwise"
    model: str = "gpt-5.6-sol"


class FakeResponsesAPI:
    def __init__(self, response: FakeParsedResponse) -> None:
        self.response = response

    def create(self, **kwargs: Any) -> FakeParsedResponse:
        return self.response


class FakeClient:
    def __init__(self, response: FakeParsedResponse) -> None:
        self.responses = FakeResponsesAPI(response)


class ScenarioAwareRunner(AgentRunner):
    model_name = "scenario-aware"
    prompt_version = "pairwise-test-v1"

    def __init__(self, case) -> None:
        self.case = case
        self.original_memory_ids = tuple(memory.id for memory in case.memories)

    def run_scenario(self, scenario, memories) -> ExecutionTrace:
        current_ids = tuple(memory.id for memory in memories)
        if current_ids == self.original_memory_ids:
            selected_action = scenario.allowed_actions[-1]
        elif current_ids == (self.case.memories[2].id,):
            selected_action = scenario.expected_action
        elif set(self.original_memory_ids) - set(current_ids) == {
            self.case.memories[0].id,
            self.case.memories[1].id,
        }:
            selected_action = scenario.expected_action
        elif not current_ids:
            selected_action = scenario.allowed_actions[-1]
        else:
            selected_action = scenario.allowed_actions[-1]

        evaluator_result = evaluate_action(scenario, selected_action)
        agent_input = scenario.to_agent_input(memories)
        memory_snapshot = [memory.to_agent_input() for memory in memories]
        return ExecutionTrace(
            trace_id=new_trace_id(),
            scenario_id=scenario.id,
            run_id=new_run_id(),
            domain=scenario.domain,
            user_input=scenario.user_input,
            agent_input=agent_input,
            requested_model=self.model_name,
            response_model=self.model_name,
            model=self.model_name,
            prompt_version=self.prompt_version,
            retrieved_memory_ids=[memory.id for memory in memories],
            memory_snapshot=memory_snapshot,
            structured_response=StructuredAgentResponse(
                selected_action=selected_action,
                action_arguments={},
                cited_memory_ids=[memory.id for memory in memories[:2]],
                concise_rationale="Scenario-aware replay test runner.",
                uncertainty=0.0,
                needs_human_review=False,
            ),
            selected_action=selected_action,
            action_arguments={},
            cited_memory_ids=[memory.id for memory in memories[:2]],
            concise_rationale="Scenario-aware replay test runner.",
            uncertainty=0.0,
            needs_human_review=False,
            evaluation=TraceEvaluation(evaluator_result=evaluator_result),
            passed=evaluator_result.passed,
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


def make_failed_trace(case):
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    wrong_action = case.scenario.allowed_actions[-1]
    trace.selected_action = wrong_action
    if trace.structured_response is not None:
        trace.structured_response.selected_action = wrong_action
    if trace.evaluation.evaluator_result is not None:
        trace.evaluation.evaluator_result.selected_action = wrong_action
        trace.evaluation.evaluator_result.passed = False
        trace.evaluation.evaluator_result.reason = "selected action differed"
    trace.passed = False
    return trace


def seed_investigation(tmp_path: Path, case, runner_factory=None):
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    trace = make_failed_trace(case)
    repository.save_trace(trace)
    session.commit()
    engine = CounterfactualReplayEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        data_dir=(Path("..").resolve() / "benchmark" / "data"),
        artifacts_dir=tmp_path / "artifacts",
        runner_factory=runner_factory,
    )
    investigation = engine.create_investigation(
        parent_trace_id=trace.trace_id,
        mode=ReplayMode.FAST,
    )
    return engine, investigation, trace


def make_pairwise_engine(tmp_path: Path, case):
    return seed_investigation(
        tmp_path,
        case,
        runner_factory=lambda parent: ScenarioAwareRunner(case),
    )


def test_unique_unordered_pair_generation(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    pair_selection = engine.generate_ranked_pairs(investigation.investigation_id)

    assert pair_selection.generated_pairs == [
        [case.memories[0].id, case.memories[1].id],
        [case.memories[0].id, case.memories[2].id],
        [case.memories[1].id, case.memories[2].id],
    ]


def test_no_self_pairs_or_duplicate_reversed_pairs(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    pairs = engine.generate_ranked_pairs(investigation.investigation_id).generated_pairs

    assert all(left != right for left, right in pairs)
    assert len(pairs) == len({tuple(pair) for pair in pairs})


def test_maximum_ten_pairs_for_five_memories(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    extra_memories = []
    for index in range(4, 7):
        memory = case.memories[0].model_copy(deep=True)
        memory.id = f"cs_01_extra_{index}"
        case.memories.append(memory)
        case.scenario.memory_ids.append(memory.id)
        extra_memories.append(memory.id)

    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    pairs = engine.generate_ranked_pairs(investigation.investigation_id).generated_pairs

    assert len(pairs) == 10


def test_pair_intervention_changes_only_two_memories(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    original_case = engine._materialize_case(investigation)  # noqa: SLF001
    target_ids = [case.memories[0].id, case.memories[1].id]
    updated_case = engine._apply_intervention(  # noqa: SLF001
        original_case.model_copy(deep=True),
        Intervention(
            intervention_type=InterventionType.DISABLE_MEMORIES,
            target_memory_ids=target_ids,
            reason="pair disablement",
        ),
    )

    for memory in updated_case.memories:
        if memory.id in target_ids:
            assert memory.status.value == "invalid"
        else:
            assert memory.model_dump(mode="json") == next(
                item.model_dump(mode="json")
                for item in original_case.memories
                if item.id == memory.id
            )


def test_pairwise_replay_uses_shared_baseline_by_default(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    artifact = engine.replay_pairwise(investigation.investigation_id, all_pairs=True)

    baseline_trace_sets = {tuple(result.original_trace_ids) for result in artifact.pair_results}
    assert artifact.shared_baseline_runs is True
    assert artifact.fresh_baseline_per_pair is False
    assert len(baseline_trace_sets) == 1


def test_fresh_baseline_per_pair_is_optional(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    artifact = engine.replay_pairwise(
        investigation.investigation_id,
        all_pairs=True,
        shared_baseline_runs=True,
        fresh_baseline_per_pair=True,
    )

    baseline_trace_sets = {tuple(result.original_trace_ids) for result in artifact.pair_results}
    assert len(baseline_trace_sets) > 1


def test_combined_influence_and_interaction_metrics(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    replay_result_a = {
        "investigation_id": investigation.investigation_id,
        "parent_trace_id": investigation.parent_trace_id,
        "scenario_id": investigation.scenario_id,
        "intervention": {
            "intervention_type": "REMOVE_MEMORY",
            "target_memory_ids": [case.memories[0].id],
            "replacement_values": {},
            "reason": "seeded individual A",
        },
        "mode": "fast",
        "total_runs": 3,
        "successful_runs": 0,
        "success_rate": 0.0,
        "confidence_interval_low": 0.0,
        "confidence_interval_high": 0.56,
        "original_successful_runs": 0,
        "original_total_runs": 3,
        "original_success_rate": 0.0,
        "influence_delta": 0.0,
        "original_action_distribution": {"ASK_FOR_INFORMATION": 3},
        "intervention_action_distribution": {"ASK_FOR_INFORMATION": 3},
        "original_replay_stability": 1.0,
        "intervention_replay_stability": 1.0,
        "original_errors": [],
        "intervention_errors": [],
        "original_trace_ids": ["trace_a"],
        "intervention_trace_ids": ["trace_b"],
    }
    replay_result_b = {
        "investigation_id": investigation.investigation_id,
        "parent_trace_id": investigation.parent_trace_id,
        "scenario_id": investigation.scenario_id,
        "intervention": {
            "intervention_type": "REMOVE_MEMORY",
            "target_memory_ids": [case.memories[1].id],
            "replacement_values": {},
            "reason": "seeded individual B",
        },
        "mode": "fast",
        "total_runs": 3,
        "successful_runs": 0,
        "success_rate": 0.0,
        "confidence_interval_low": 0.0,
        "confidence_interval_high": 0.56,
        "original_successful_runs": 0,
        "original_total_runs": 3,
        "original_success_rate": 0.0,
        "influence_delta": 0.0,
        "original_action_distribution": {"ASK_FOR_INFORMATION": 3},
        "intervention_action_distribution": {"ASK_FOR_INFORMATION": 3},
        "original_replay_stability": 1.0,
        "intervention_replay_stability": 1.0,
        "original_errors": [],
        "intervention_errors": [],
        "original_trace_ids": ["trace_c"],
        "intervention_trace_ids": ["trace_d"],
    }
    investigation = investigation.model_copy(
        update={
            "replay_results": [
                ReplayResult.model_validate(replay_result_a),
                ReplayResult.model_validate(replay_result_b),
            ]
        }
    )
    path = (
        tmp_path
        / "artifacts"
        / "investigations"
        / investigation.investigation_id
        / "investigation.json"
    )
    path.write_text(investigation.model_dump_json(indent=2), encoding="utf-8")

    artifact = engine.replay_pairwise(
        investigation.investigation_id,
        memory_a=case.memories[0].id,
        memory_b=case.memories[1].id,
    )
    result = artifact.pair_results[0]

    assert result.combined_influence == pytest.approx(1.0)
    assert result.interaction_score == pytest.approx(1.0)
    assert result.interaction_synergy == pytest.approx(1.0)
    assert result.evidence_classification == PairEvidenceClassification.INTERACTION_SUPPORTED


def test_pair_dominated_by_one_individual_memory(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    replay_result = {
        "investigation_id": investigation.investigation_id,
        "parent_trace_id": investigation.parent_trace_id,
        "scenario_id": investigation.scenario_id,
        "intervention": {
            "intervention_type": "REMOVE_MEMORY",
            "target_memory_ids": [case.memories[0].id],
            "replacement_values": {},
            "reason": "seeded strong individual",
        },
        "mode": "fast",
        "total_runs": 3,
        "successful_runs": 3,
        "success_rate": 1.0,
        "confidence_interval_low": 0.43,
        "confidence_interval_high": 1.0,
        "original_successful_runs": 0,
        "original_total_runs": 3,
        "original_success_rate": 0.0,
        "influence_delta": 1.0,
        "original_action_distribution": {"ASK_FOR_INFORMATION": 3},
        "intervention_action_distribution": {"ISSUE_REFUND": 3},
        "original_replay_stability": 1.0,
        "intervention_replay_stability": 1.0,
        "original_errors": [],
        "intervention_errors": [],
        "original_trace_ids": ["trace_e"],
        "intervention_trace_ids": ["trace_f"],
    }
    investigation = investigation.model_copy(
        update={"replay_results": [ReplayResult.model_validate(replay_result)]}
    )
    path = (
        tmp_path
        / "artifacts"
        / "investigations"
        / investigation.investigation_id
        / "investigation.json"
    )
    path.write_text(investigation.model_dump_json(indent=2), encoding="utf-8")

    artifact = engine.replay_pairwise(
        investigation.investigation_id,
        memory_a=case.memories[0].id,
        memory_b=case.memories[1].id,
    )
    result = artifact.pair_results[0]

    assert result.evidence_classification == PairEvidenceClassification.DOMINATED_BY_ONE_MEMORY


def test_no_memory_and_isolation_controls(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    no_memory = engine.run_no_memory_control(investigation.investigation_id)
    isolated = engine.run_isolate_memory(investigation.investigation_id, case.memories[2].id)

    assert no_memory.control_type == MemoryControlType.NO_MEMORY
    assert isolated.control_type == MemoryControlType.ISOLATE_MEMORY
    assert isolated.target_memory_id == case.memories[2].id


def test_memory_dependence_classification_and_support_audit(
    tmp_path: Path, benchmark_cases
) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, _ = make_pairwise_engine(tmp_path, case)
    controls = engine.export_memory_controls(investigation.investigation_id)
    pairwise = engine.replay_pairwise(investigation.investigation_id, all_pairs=True)

    assert (
        controls.memory_dependence_classification
        == MemoryDependenceClassification.LIKELY_MEMORY_INDEPENDENT
    )
    assert (
        pairwise.memory_dependence_classification
        == MemoryDependenceClassification.PAIRWISE_MEMORY_DEPENDENT
    )
    assert any(result.support_validity.outcome_correct for result in pairwise.pair_results)


def test_pairwise_persistence_and_parent_child_relationships(
    tmp_path: Path, benchmark_cases
) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    engine, investigation, trace = make_pairwise_engine(tmp_path, case)
    artifact = engine.replay_pairwise(investigation.investigation_id, all_pairs=True)
    controls = engine.export_memory_controls(investigation.investigation_id)

    investigation_dir = tmp_path / "artifacts" / "investigations" / investigation.investigation_id
    assert (investigation_dir / "pairwise-replay.json").exists()
    assert (investigation_dir / "memory-controls.json").exists()
    stored_trace = engine.repository.get_trace(artifact.pair_results[0].intervention_trace_ids[0])
    assert stored_trace is not None
    assert stored_trace.parent_trace_id == trace.trace_id
    assert controls.no_memory_control.control_trace_ids


def test_mocked_openai_pairwise_execution(tmp_path: Path, benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    trace = make_failed_trace(case)
    trace.requested_model = "gpt-5.6"
    trace.response_model = "gpt-5.6-sol"
    trace.prompt_version = "v1"
    repository.save_trace(trace)
    session.commit()

    decision = OpenAIActionSelection(
        selected_action=case.scenario.expected_action,
        action_arguments=[],
        cited_memory_ids=[case.memories[2].id],
        concise_rationale="pairwise mocked response",
        uncertainty=0.1,
        needs_human_review=False,
    )

    def factory(parent_trace):
        settings = OpenAISettings(
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
        return OpenAIAgentRunner(
            settings=settings,
            client=FakeClient(
                FakeParsedResponse(
                    output_text=decision.model_dump_json(),
                    usage=FakeUsage(),
                )
            ),
        )

    engine = CounterfactualReplayEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        data_dir=(Path("..").resolve() / "benchmark" / "data"),
        artifacts_dir=tmp_path / "artifacts",
        runner_factory=factory,
    )
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    artifact = engine.replay_pairwise(investigation.investigation_id, all_pairs=True)

    assert artifact.pair_results
    assert artifact.pair_results[0].intervention_trace_ids
