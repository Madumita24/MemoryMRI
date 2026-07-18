from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIActionSelection, OpenAIAgentRunner
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import Intervention, InterventionType, ReplayMode


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
    id: str = "resp_replay"
    model: str = "gpt-5.6-sol"


class FakeResponsesAPI:
    def __init__(self, response: FakeParsedResponse) -> None:
        self.response = response

    def create(self, **kwargs: Any) -> FakeParsedResponse:
        return self.response


class FakeClient:
    def __init__(self, response: FakeParsedResponse) -> None:
        self.responses = FakeResponsesAPI(response)


def make_failed_trace(benchmark_cases):
    case = benchmark_cases[0].model_copy(deep=True)
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
    return case, trace


def seed_failed_trace(tmp_path: Path, benchmark_cases):
    case, trace = make_failed_trace(benchmark_cases)
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    repository.save_trace(trace)
    session.commit()
    return case, trace


def make_engine(tmp_path: Path, runner_factory=None) -> CounterfactualReplayEngine:
    return CounterfactualReplayEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        data_dir=(Path("..").resolve() / "benchmark" / "data"),
        artifacts_dir=tmp_path / "artifacts",
        runner_factory=runner_factory,
    )


def test_original_snapshot_preservation(tmp_path: Path, benchmark_cases) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path, runner_factory=lambda parent: FakeAgentRunner())
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    before = [memory.model_dump(mode="json") for memory in investigation.original_memory_snapshot]

    engine.replay_without_memory(
        investigation.investigation_id,
        investigation.original_memory_snapshot[0].memory_id,
    )
    after = [
        memory.model_dump(mode="json")
        for memory in engine.load_investigation(
            investigation.investigation_id
        ).original_memory_snapshot
    ]
    assert before == after


def test_individual_removal_changes_only_one_memory(tmp_path: Path, benchmark_cases) -> None:
    case, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path)
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    target_memory_id = investigation.original_memory_snapshot[0].memory_id

    removed_case = engine._apply_intervention(  # noqa: SLF001
        engine._materialize_case(investigation),  # noqa: SLF001
        Intervention(
            intervention_type=InterventionType.REMOVE_MEMORY,
            target_memory_ids=[target_memory_id],
            reason="test removal",
        ),
    )

    assert target_memory_id not in removed_case.scenario.memory_ids
    original_other_ids = [memory.id for memory in case.memories if memory.id != target_memory_id]
    removed_ids = [memory.id for memory in removed_case.memories]
    assert removed_ids == original_other_ids


def test_individual_disablement_marks_only_target_invalid(tmp_path: Path, benchmark_cases) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path)
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    target_memory_id = investigation.original_memory_snapshot[0].memory_id

    disabled_case = engine._apply_intervention(  # noqa: SLF001
        engine._materialize_case(investigation),  # noqa: SLF001
        Intervention(
            intervention_type=InterventionType.DISABLE_MEMORY,
            target_memory_ids=[target_memory_id],
            reason="test disablement",
        ),
    )

    target = next(memory for memory in disabled_case.memories if memory.id == target_memory_id)
    others = [memory for memory in disabled_case.memories if memory.id != target_memory_id]
    assert target.status.value == "invalid"
    assert all(memory.status.value != "invalid" for memory in others)


def test_only_one_memory_changes_during_disable(tmp_path: Path, benchmark_cases) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path)
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    original_case = engine._materialize_case(investigation)  # noqa: SLF001
    target_memory_id = investigation.original_memory_snapshot[0].memory_id
    disabled_case = engine._apply_intervention(  # noqa: SLF001
        original_case.model_copy(deep=True),
        Intervention(
            intervention_type=InterventionType.DISABLE_MEMORY,
            target_memory_ids=[target_memory_id],
            reason="test disablement",
        ),
    )

    for original_memory, disabled_memory in zip(
        original_case.memories, disabled_case.memories, strict=True
    ):
        if original_memory.id == target_memory_id:
            assert disabled_memory.status.value == "invalid"
            continue
        assert disabled_memory.model_dump(mode="json") == original_memory.model_dump(mode="json")


def test_influence_and_action_distribution_metrics(tmp_path: Path, benchmark_cases) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path, runner_factory=lambda parent: FakeAgentRunner())
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    result = engine.replay_without_memory(
        investigation.investigation_id,
        investigation.original_memory_snapshot[0].memory_id,
    )

    assert result.original_total_runs == 3
    assert result.total_runs == 3
    assert result.influence_delta == pytest.approx(
        result.success_rate - result.original_success_rate
    )
    assert isinstance(result.original_action_distribution, dict)
    assert isinstance(result.intervention_action_distribution, dict)
    assert 0.0 <= result.confidence_interval_low <= result.confidence_interval_high <= 1.0


def test_replay_persistence_and_parent_child_trace_relationship(
    tmp_path: Path, benchmark_cases
) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path, runner_factory=lambda parent: FakeAgentRunner())
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    result = engine.replay_with_memory_disabled(
        investigation.investigation_id,
        investigation.original_memory_snapshot[0].memory_id,
    )

    investigation_dir = tmp_path / "artifacts" / "investigations" / investigation.investigation_id
    assert (investigation_dir / "investigation.json").exists()
    assert (investigation_dir / "individual-replay.json").exists()
    assert (investigation_dir / "individual-replay.md").exists()

    stored_trace = engine.repository.get_trace(result.intervention_trace_ids[0])
    assert stored_trace is not None
    assert stored_trace.parent_trace_id == trace.trace_id
    assert stored_trace.investigation_id == investigation.investigation_id
    assert stored_trace.replay_intervention is not None
    assert stored_trace.replay_role == "replay_intervention"


def test_fake_runner_replay_is_deterministic(tmp_path: Path, benchmark_cases) -> None:
    _, trace = seed_failed_trace(tmp_path, benchmark_cases)
    engine = make_engine(tmp_path, runner_factory=lambda parent: FakeAgentRunner())
    investigation = engine.create_investigation(
        parent_trace_id=trace.trace_id,
        mode=ReplayMode.FAST,
    )
    result = engine.replay_without_memory(
        investigation.investigation_id,
        investigation.original_memory_snapshot[0].memory_id,
    )

    assert result.original_replay_stability == 1.0
    assert result.intervention_replay_stability == 1.0


def test_mocked_openai_replay(tmp_path: Path, benchmark_cases) -> None:
    case, trace = make_failed_trace(benchmark_cases)
    trace.requested_model = "gpt-5.6"
    trace.response_model = "gpt-5.6-sol"
    trace.prompt_version = "v1"
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    repository.save_trace(trace)
    session.commit()

    decision = OpenAIActionSelection(
        selected_action=case.scenario.expected_action,
        action_arguments=[],
        cited_memory_ids=[case.memories[1].id, case.memories[2].id],
        concise_rationale="mocked replay response",
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

    engine = make_engine(tmp_path, runner_factory=factory)
    investigation = engine.create_investigation(parent_trace_id=trace.trace_id)
    result = engine.replay_without_memory(
        investigation.investigation_id,
        investigation.original_memory_snapshot[0].memory_id,
    )

    assert result.total_runs == 3
    assert result.successful_runs == 3
    assert result.original_trace_ids
    assert result.intervention_trace_ids
