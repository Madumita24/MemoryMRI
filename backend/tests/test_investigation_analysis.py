from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from openai import APITimeoutError

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.analysis.models import (
    ContradictionAnalysisInput,
    ContradictionPairInput,
    ReplayComparisonClassification,
    SuspicionAnalysisInput,
)
from memory_mri.analysis.scoring import (
    build_deterministic_pair_observations,
    score_memories,
    summarize_replay_evidence,
)
from memory_mri.analysis.semantic import (
    InvestigationSemanticAnalyzer,
    SemanticAnalysisError,
)
from memory_mri.config import (
    OpenAISettings,
    SemanticAnalysisSettings,
    SuspicionScoringConfig,
)
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.prompts.loader import load_analysis_prompt
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    Intervention,
    InterventionType,
    ReplayMode,
    ReplayResult,
)


@dataclass
class FakeUsage:
    input_tokens: int = 12
    output_tokens: int = 6
    total_tokens: int = 18

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
    id: str = "resp_analysis"
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


def make_settings(tmp_path: Path, *, cache_enabled: bool = False) -> OpenAISettings:
    return OpenAISettings(
        api_key="test-key",
        model="gpt-5.6",
        timeout_seconds=5.0,
        max_retries=0,
        cache_enabled=cache_enabled,
        prompt_version="v1",
        reasoning_effort=None,
        verbosity="low",
        cache_dir=tmp_path / "openai-cache",
    )


def make_failed_trace(case):
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    wrong_action = case.scenario.allowed_actions[-1]
    trace.requested_model = "gpt-5.6"
    trace.response_model = "gpt-5.6-sol"
    trace.model = "gpt-5.6-sol"
    trace.prompt_version = "v1"
    trace.selected_action = wrong_action
    trace.concise_rationale = "Mocked failed rationale."
    trace.cited_memory_ids = [case.memories[0].id]
    if trace.structured_response is not None:
        trace.structured_response.selected_action = wrong_action
        trace.structured_response.concise_rationale = "Mocked failed rationale."
        trace.structured_response.cited_memory_ids = [case.memories[0].id]
    if trace.evaluation.evaluator_result is not None:
        trace.evaluation.evaluator_result.selected_action = wrong_action
        trace.evaluation.evaluator_result.passed = False
        trace.evaluation.evaluator_result.reason = "selected action differed"
    trace.passed = False
    return trace


def seed_investigation(tmp_path: Path, case, replay_results: list[ReplayResult] | None = None):
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    trace = make_failed_trace(case)
    repository.save_trace(trace)
    session.commit()

    engine = CounterfactualReplayEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        data_dir=Path(__file__).resolve().parents[2] / "benchmark" / "data",
        artifacts_dir=tmp_path / "artifacts",
        runner_factory=lambda parent: FakeAgentRunner(),
    )
    investigation = engine.create_investigation(
        parent_trace_id=trace.trace_id,
        mode=ReplayMode.FAST,
    )
    if replay_results is not None:
        updated = investigation.model_copy(deep=True)
        updated.replay_results = replay_results
        path = (
            tmp_path
            / "artifacts"
            / "investigations"
            / investigation.investigation_id
            / "investigation.json"
        )
        path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        investigation = updated
    return trace, investigation


def make_memory_analyses(case) -> FakeParsedResponse:
    analyses = {
        "analyses": [
            {
                "memory_id": memory.id,
                "semantic_suspicion_score": 0.9 if index == 0 else 0.2,
                "suspected_issue_types": ["wrong_context"] if index == 0 else ["none"],
                "concise_reason": f"semantic concern for {memory.id}",
                "related_memory_ids": [case.memories[1].id] if index == 0 else [],
                "uncertainty": 0.2,
                "requires_human_review": False,
            }
            for index, memory in enumerate(case.memories)
        ]
    }
    return FakeParsedResponse(
        output_text=json.dumps(analyses),
        usage=FakeUsage(),
    )


def make_pair_analyses(case) -> FakeParsedResponse:
    pairs = {
        "pairs": [
            {
                "memory_a_id": case.memories[0].id,
                "memory_b_id": case.memories[1].id,
                "relationship": "unrelated",
                "concise_explanation": "No semantic conflict detected.",
                "confidence": 0.4,
                "requires_human_review": False,
            },
            {
                "memory_a_id": case.memories[0].id,
                "memory_b_id": case.memories[2].id,
                "relationship": "potentially_consistent",
                "concise_explanation": "The pair could coexist.",
                "confidence": 0.5,
                "requires_human_review": False,
            },
            {
                "memory_a_id": case.memories[1].id,
                "memory_b_id": case.memories[2].id,
                "relationship": "unrelated",
                "concise_explanation": "No contradiction detected.",
                "confidence": 0.3,
                "requires_human_review": False,
            },
        ]
    }
    return FakeParsedResponse(
        output_text=json.dumps(pairs),
        usage=FakeUsage(),
    )


def test_stale_expired_superseded_entity_and_priority_signals(benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    case.memories[0].status = case.memories[0].status.STALE
    case.memories[0].valid_until = datetime(2025, 1, 1, tzinfo=timezone.utc)
    case.memories[0].retrieval_priority = 99
    case.memories[0].operational_metadata["entity_match"] = False
    case.memories[1].status = case.memories[1].status.SUPERSEDED
    pair_observations = build_deterministic_pair_observations(
        [memory.to_agent_input() for memory in case.memories]
    )

    results = score_memories(
        memories=[memory.to_agent_input() for memory in case.memories],
        cited_memory_ids=[case.memories[0].id],
        pair_observations=pair_observations,
        config=SuspicionScoringConfig(),
    )
    by_id = {result.memory_id: result for result in results}
    stale_signals = {
        observation.signal_name: observation
        for observation in by_id[case.memories[0].id].metadata_observations
    }
    superseded_signals = {
        observation.signal_name: observation
        for observation in by_id[case.memories[1].id].metadata_observations
    }

    assert stale_signals["stale_status"].signal_present is True
    assert stale_signals["expired_validity"].signal_present is True
    assert stale_signals["entity_mismatch"].signal_present is True
    assert stale_signals["unusually_high_retrieval_priority"].signal_present is True
    assert superseded_signals["superseded_status"].signal_present is True


def test_missing_validity_and_configurable_weights_are_documented(benchmark_cases) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    case.memories[0].valid_from = None
    config = SuspicionScoringConfig(
        unusually_high_retrieval_priority=3.0,
        high_priority_threshold=80,
    )
    results = score_memories(
        memories=[memory.to_agent_input() for memory in case.memories],
        cited_memory_ids=[],
        pair_observations=[],
        config=config,
    )
    signals = {
        observation.signal_name: observation for observation in results[0].metadata_observations
    }

    assert signals["missing_validity_dates"].signal_present is True
    assert 0.0 <= results[0].deterministic_score <= 1.0
    assert config.documented_weights()["signal_weights"]["unusually_high_retrieval_priority"] == 3.0


def test_benchmark_private_fields_do_not_affect_deterministic_scores(benchmark_cases) -> None:
    first = benchmark_cases[0].model_copy(deep=True)
    second = benchmark_cases[0].model_copy(deep=True)
    second.scenario.expected_action = second.scenario.allowed_actions[0]
    second.scenario.expected_problematic_memory_ids = ["sentinel_problematic_memory"]
    second.scenario.failure_category = "SENTINEL_FAILURE_CATEGORY"
    second.scenario.explanation = "SENTINEL_EXPLANATION"

    first_results = score_memories(
        memories=[memory.to_agent_input() for memory in first.memories],
        cited_memory_ids=[first.memories[0].id],
        pair_observations=[],
        config=SuspicionScoringConfig(),
    )
    second_results = score_memories(
        memories=[memory.to_agent_input() for memory in second.memories],
        cited_memory_ids=[second.memories[0].id],
        pair_observations=[],
        config=SuspicionScoringConfig(),
    )

    assert [result.deterministic_score for result in first_results] == [
        result.deterministic_score for result in second_results
    ]


def test_benchmark_private_fields_never_reach_semantic_prompts(
    benchmark_cases, tmp_path: Path
) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    case.scenario.expected_action = "SENTINEL_EXPECTED_ACTION"
    case.scenario.failure_category = "SENTINEL_FAILURE_CATEGORY"
    case.scenario.expected_problematic_memory_ids = ["SENTINEL_MEMORY"]
    case.scenario.explanation = "SENTINEL_EXPLANATION"
    _, investigation = seed_investigation(tmp_path, case)
    client = FakeClient([make_memory_analyses(case)])
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings(
            suspicion_prompt_version="v1",
            contradiction_prompt_version="v1",
        ),
        client=client,
    )
    engine = InvestigationAnalysisEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        artifacts_dir=tmp_path / "artifacts",
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings(
            suspicion_prompt_version="v1",
            contradiction_prompt_version="v1",
        ),
        semantic_analyzer=analyzer,
    )

    engine.rank_memories(investigation.investigation_id)

    request_text = client.responses.calls[0]["input"][0]["content"][0]["text"]
    instructions = client.responses.calls[0]["instructions"]
    combined = f"{instructions}\n{request_text}"
    assert "SENTINEL_EXPECTED_ACTION" not in combined
    assert "SENTINEL_FAILURE_CATEGORY" not in combined
    assert "SENTINEL_MEMORY" not in combined
    assert "SENTINEL_EXPLANATION" not in combined
    assert "expected_action" not in combined
    assert "failure_category" not in combined


def test_invalid_gpt_memory_ids_and_related_ids_are_rejected(
    benchmark_cases, tmp_path: Path
) -> None:
    case = benchmark_cases[0]
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient(
            [
                FakeParsedResponse(
                    output_text=json.dumps(
                        {
                            "analyses": [
                                {
                                    "memory_id": "missing_memory",
                                    "semantic_suspicion_score": 0.9,
                                    "suspected_issue_types": ["wrong_context"],
                                    "concise_reason": "bad id",
                                    "related_memory_ids": [],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_id": case.memories[1].id,
                                    "semantic_suspicion_score": 0.1,
                                    "suspected_issue_types": ["none"],
                                    "concise_reason": "ok",
                                    "related_memory_ids": [],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_id": case.memories[2].id,
                                    "semantic_suspicion_score": 0.1,
                                    "suspected_issue_types": ["none"],
                                    "concise_reason": "ok",
                                    "related_memory_ids": [],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                            ]
                        }
                    )
                )
            ]
        ),
    )
    payload = SuspicionAnalysisInput(
        scenario_id=case.scenario.id,
        domain=case.scenario.domain,
        user_request=case.scenario.user_input,
        allowed_actions=case.scenario.allowed_actions,
        original_selected_action=case.scenario.allowed_actions[-1],
        concise_original_rationale="mocked",
        memories=[memory.to_agent_input() for memory in case.memories],
    )
    with pytest.raises(SemanticAnalysisError) as exc_info:
        analyzer.analyze_memory_suspicion(payload)
    assert exc_info.value.failure.code == "invalid_memory_id"

    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient(
            [
                FakeParsedResponse(
                    output_text=json.dumps(
                        {
                            "analyses": [
                                {
                                    "memory_id": case.memories[0].id,
                                    "semantic_suspicion_score": 0.9,
                                    "suspected_issue_types": ["wrong_context"],
                                    "concise_reason": "bad related id",
                                    "related_memory_ids": ["missing_related"],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_id": case.memories[1].id,
                                    "semantic_suspicion_score": 0.1,
                                    "suspected_issue_types": ["none"],
                                    "concise_reason": "ok",
                                    "related_memory_ids": [],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_id": case.memories[2].id,
                                    "semantic_suspicion_score": 0.1,
                                    "suspected_issue_types": ["none"],
                                    "concise_reason": "ok",
                                    "related_memory_ids": [],
                                    "uncertainty": 0.1,
                                    "requires_human_review": False,
                                },
                            ]
                        }
                    )
                )
            ]
        ),
    )
    with pytest.raises(SemanticAnalysisError) as exc_info:
        analyzer.analyze_memory_suspicion(payload)
    assert exc_info.value.failure.code == "invalid_related_memory_ids"


def test_invalid_relationship_types_and_duplicate_pair_ordering_are_rejected(
    benchmark_cases, tmp_path: Path
) -> None:
    case = benchmark_cases[0]
    payload = ContradictionAnalysisInput(
        scenario_id=case.scenario.id,
        domain=case.scenario.domain,
        user_request=case.scenario.user_input,
        allowed_actions=case.scenario.allowed_actions,
        original_selected_action=case.scenario.allowed_actions[-1],
        concise_original_rationale="mocked",
        memories=[memory.to_agent_input() for memory in case.memories],
        pairs=[
            ContradictionPairInput(
                memory_a_id=case.memories[0].id,
                memory_b_id=case.memories[1].id,
            ),
            ContradictionPairInput(
                memory_a_id=case.memories[0].id,
                memory_b_id=case.memories[2].id,
            ),
            ContradictionPairInput(
                memory_a_id=case.memories[1].id,
                memory_b_id=case.memories[2].id,
            ),
        ],
    )
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient(
            [
                FakeParsedResponse(
                    output_text=json.dumps(
                        {
                            "pairs": [
                                {
                                    "memory_a_id": case.memories[0].id,
                                    "memory_b_id": case.memories[1].id,
                                    "relationship": "not_valid",
                                    "concise_explanation": "bad type",
                                    "confidence": 0.1,
                                    "requires_human_review": False,
                                }
                            ]
                        }
                    )
                )
            ]
        ),
    )
    with pytest.raises(SemanticAnalysisError) as exc_info:
        analyzer.analyze_pair_relationships(payload)
    assert exc_info.value.failure.code == "invalid_model_output"

    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient(
            [
                FakeParsedResponse(
                    output_text=json.dumps(
                        {
                            "pairs": [
                                {
                                    "memory_a_id": case.memories[1].id,
                                    "memory_b_id": case.memories[0].id,
                                    "relationship": "unrelated",
                                    "concise_explanation": "wrong order",
                                    "confidence": 0.2,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_a_id": case.memories[0].id,
                                    "memory_b_id": case.memories[2].id,
                                    "relationship": "unrelated",
                                    "concise_explanation": "ok",
                                    "confidence": 0.2,
                                    "requires_human_review": False,
                                },
                                {
                                    "memory_a_id": case.memories[1].id,
                                    "memory_b_id": case.memories[2].id,
                                    "relationship": "unrelated",
                                    "concise_explanation": "ok",
                                    "confidence": 0.2,
                                    "requires_human_review": False,
                                },
                            ]
                        }
                    )
                )
            ]
        ),
    )
    with pytest.raises(SemanticAnalysisError) as exc_info:
        analyzer.analyze_pair_relationships(payload)
    assert exc_info.value.failure.code == "noncanonical_pair_order"


def test_unrelated_is_accepted_as_valid_semantic_result(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    payload = ContradictionAnalysisInput(
        scenario_id=case.scenario.id,
        domain=case.scenario.domain,
        user_request=case.scenario.user_input,
        allowed_actions=case.scenario.allowed_actions,
        original_selected_action=case.scenario.allowed_actions[-1],
        concise_original_rationale="mocked",
        memories=[memory.to_agent_input() for memory in case.memories],
        pairs=[
            ContradictionPairInput(
                memory_a_id=case.memories[0].id,
                memory_b_id=case.memories[1].id,
            ),
            ContradictionPairInput(
                memory_a_id=case.memories[0].id,
                memory_b_id=case.memories[2].id,
            ),
            ContradictionPairInput(
                memory_a_id=case.memories[1].id,
                memory_b_id=case.memories[2].id,
            ),
        ],
    )
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient([make_pair_analyses(case)]),
    )
    result = analyzer.analyze_pair_relationships(payload)

    assert any(pair.relationship.value == "unrelated" for pair in result.analyses)


def test_semantic_score_never_becomes_replay_influence_and_zero_persists_in_export(
    benchmark_cases, tmp_path: Path
) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    _, investigation = seed_investigation(
        tmp_path,
        case,
        replay_results=[
            ReplayResult(
                investigation_id="inv_test",
                parent_trace_id="trace_parent",
                scenario_id=case.scenario.id,
                intervention=Intervention(
                    intervention_type=InterventionType.REMOVE_MEMORY,
                    target_memory_ids=[case.memories[0].id],
                    reason="test",
                ),
                mode=ReplayMode.FAST,
                total_runs=3,
                successful_runs=0,
                success_rate=0.0,
                confidence_interval_low=0.0,
                confidence_interval_high=0.56,
                original_successful_runs=0,
                original_total_runs=3,
                original_success_rate=0.0,
                influence_delta=0.0,
                original_action_distribution={"ASK_FOR_INFORMATION": 3},
                intervention_action_distribution={"ASK_FOR_INFORMATION": 3},
                original_replay_stability=1.0,
                intervention_replay_stability=1.0,
                original_errors=[],
                intervention_errors=[],
                original_trace_ids=["trace_a"],
                intervention_trace_ids=["trace_b"],
            )
        ],
    )
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient([make_memory_analyses(case)]),
    )
    engine = InvestigationAnalysisEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        artifacts_dir=tmp_path / "artifacts",
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        semantic_analyzer=analyzer,
    )

    artifact = engine.rank_memories(investigation.investigation_id)
    first_memory = artifact.memories[0]
    stored = json.loads(
        (
            tmp_path
            / "artifacts"
            / "investigations"
            / investigation.investigation_id
            / "suspicion-ranking.json"
        ).read_text(encoding="utf-8")
    )

    assert first_memory.semantic_score >= 0.0
    assert first_memory.replay_supported_evidence.observed_individual_influence == 0.0
    assert (
        stored["memories"][0]["replay_supported_evidence"]["observed_individual_influence"] == 0.0
    )
    assert (
        first_memory.comparison_classification
        == ReplayComparisonClassification.NOT_SUPPORTED_BY_REPLAY
    )


def test_comparison_classifications_are_correct() -> None:
    no_replay_summary, no_replay_classification = summarize_replay_evidence(
        memory_id="memory_1",
        replay_results=[],
        suspicion_score=0.2,
    )
    assert no_replay_summary.replay_evidence_available is False
    assert no_replay_classification == ReplayComparisonClassification.NOT_REPLAY_TESTED

    replay_result = ReplayResult(
        investigation_id="inv_test",
        parent_trace_id="trace_parent",
        scenario_id="scenario_1",
        intervention=Intervention(
            intervention_type=InterventionType.REMOVE_MEMORY,
            target_memory_ids=["memory_1"],
            reason="test",
        ),
        mode=ReplayMode.FAST,
        total_runs=3,
        successful_runs=2,
        success_rate=0.67,
        confidence_interval_low=0.2,
        confidence_interval_high=0.94,
        original_successful_runs=0,
        original_total_runs=3,
        original_success_rate=0.0,
        influence_delta=0.67,
        original_action_distribution={"A": 3},
        intervention_action_distribution={"B": 3},
        original_replay_stability=1.0,
        intervention_replay_stability=1.0,
        original_errors=[],
        intervention_errors=[],
        original_trace_ids=["trace_a"],
        intervention_trace_ids=["trace_b"],
    )
    _, supported = summarize_replay_evidence(
        memory_id="memory_1",
        replay_results=[replay_result],
        suspicion_score=0.9,
    )
    _, low_suspicion_effect = summarize_replay_evidence(
        memory_id="memory_1",
        replay_results=[replay_result],
        suspicion_score=0.1,
    )

    assert supported == ReplayComparisonClassification.SUPPORTED_BY_REPLAY
    assert low_suspicion_effect == ReplayComparisonClassification.LOW_SUSPICION_BUT_EFFECT_OBSERVED


def test_cached_semantic_results_are_revalidated(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    settings = make_settings(tmp_path, cache_enabled=True)
    analyzer = InvestigationSemanticAnalyzer(
        settings=settings,
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient([]),
    )
    payload = SuspicionAnalysisInput(
        scenario_id=case.scenario.id,
        domain=case.scenario.domain,
        user_request=case.scenario.user_input,
        allowed_actions=case.scenario.allowed_actions,
        original_selected_action=case.scenario.allowed_actions[-1],
        concise_original_rationale="mocked",
        memories=[memory.to_agent_input() for memory in case.memories],
    )
    prompt_content_hash = hashlib.sha256(
        load_analysis_prompt("memory_suspicion", "v1").encode("utf-8")
    ).hexdigest()
    prompt_hash = analyzer._cache_key(  # noqa: SLF001
        "memory_suspicion",
        payload.model_dump(mode="json"),
        prompt_content_hash,
    )
    cache_path = settings.cache_dir / "semantic_analysis" / f"{prompt_hash}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "request_hash": prompt_hash,
                "analysis_kind": "memory_suspicion",
                "requested_model": "gpt-5.6",
                "response_model": "gpt-5.6-sol",
                "prompt_version": "v1",
                "prompt_content_hash": prompt_content_hash,
                "payload": payload.model_dump(mode="json"),
                "structured_output": {
                    "analyses": [
                        {
                            "memory_id": case.memories[0].id,
                            "semantic_suspicion_score": 0.8,
                            "suspected_issue_types": ["wrong_context"],
                            "concise_reason": "cached",
                            "related_memory_ids": ["missing_memory"],
                            "uncertainty": 0.2,
                            "requires_human_review": False,
                        },
                        {
                            "memory_id": case.memories[1].id,
                            "semantic_suspicion_score": 0.2,
                            "suspected_issue_types": ["none"],
                            "concise_reason": "cached",
                            "related_memory_ids": [],
                            "uncertainty": 0.2,
                            "requires_human_review": False,
                        },
                        {
                            "memory_id": case.memories[2].id,
                            "semantic_suspicion_score": 0.2,
                            "suspected_issue_types": ["none"],
                            "concise_reason": "cached",
                            "related_memory_ids": [],
                            "uncertainty": 0.2,
                            "requires_human_review": False,
                        },
                    ]
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "original_model_latency_ms": 10,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(SemanticAnalysisError) as exc_info:
        analyzer.analyze_memory_suspicion(payload)
    assert exc_info.value.failure.code == "invalid_related_memory_ids"


def test_api_failures_are_not_converted_into_suspicion_scores(
    benchmark_cases, tmp_path: Path
) -> None:
    case = benchmark_cases[0]
    _, investigation = seed_investigation(tmp_path, case)
    analyzer = InvestigationSemanticAnalyzer(
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        client=FakeClient([APITimeoutError(request=None)]),  # type: ignore[arg-type]
    )
    engine = InvestigationAnalysisEngine(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        artifacts_dir=tmp_path / "artifacts",
        settings=make_settings(tmp_path),
        prompt_settings=SemanticAnalysisSettings("v1", "v1"),
        semantic_analyzer=analyzer,
    )

    with pytest.raises(SemanticAnalysisError) as exc_info:
        engine.rank_memories(investigation.investigation_id)

    assert exc_info.value.failure.code == "transient_openai_error"
    assert not (
        tmp_path
        / "artifacts"
        / "investigations"
        / investigation.investigation_id
        / "suspicion-ranking.json"
    ).exists()
