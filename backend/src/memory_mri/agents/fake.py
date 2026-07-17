from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timezone

from memory_mri.agents.base import AgentRunner
from memory_mri.evaluation import evaluate_action
from memory_mri.schemas import (
    AgentScenario,
    ExecutionTrace,
    Memory,
    StructuredAgentResponse,
    TraceCacheStatus,
    TraceEvaluation,
    new_run_id,
    new_trace_id,
)


@dataclass(frozen=True)
class MemoryAssessment:
    memory: Memory
    supports_action: str | None
    score: float
    reasons: tuple[str, ...]


class FakeAgentRunner(AgentRunner):
    """Deterministic heuristic runner for benchmark baselines.

    The runner intentionally mixes correct and incorrect behavior. It scores
    candidate action memories from reviewed metadata rather than scenario IDs.
    The score combines retrieval priority, memory status, evidence role,
    confidence, entity match, explicit ignore hints, and pairwise interaction
    boosts. This yields realistic baseline failures without forcing every case
    to fail.
    """

    model_name = "fake-deterministic"
    prompt_version = "day1-5-v1"

    def run_scenario(self, scenario: AgentScenario, memories: list[Memory]) -> ExecutionTrace:
        scenario_memories = [memory for memory in memories if memory.id in scenario.memory_ids]
        retrieved = sorted(
            scenario_memories,
            key=lambda memory: (-memory.retrieval_priority, memory.created_at),
        )
        assessments = self._assess_memories(scenario, retrieved)
        selected_action = self._choose_action(scenario, assessments)
        evaluator_result = evaluate_action(scenario, selected_action)
        action_arguments = {
            "heuristic_version": self.prompt_version,
            "top_memory_ids": ",".join(assessment.memory.id for assessment in assessments[:3]),
        }
        memory_snapshot = [memory.to_agent_input() for memory in retrieved]
        agent_input = scenario.to_agent_input(retrieved)
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
            retrieved_memory_ids=[memory.id for memory in retrieved],
            memory_snapshot=memory_snapshot,
            structured_response=StructuredAgentResponse(
                selected_action=selected_action,
                action_arguments=action_arguments,
                cited_memory_ids=[assessment.memory.id for assessment in assessments[:3]],
                concise_rationale="Deterministic heuristic selected the highest-scoring action.",
                uncertainty=0.0 if evaluator_result.passed else 0.35,
                needs_human_review=False,
            ),
            selected_action=selected_action,
            action_arguments=action_arguments,
            cited_memory_ids=[assessment.memory.id for assessment in assessments[:3]],
            concise_rationale="Deterministic heuristic selected the highest-scoring action.",
            uncertainty=0.0 if evaluator_result.passed else 0.35,
            needs_human_review=False,
            tool_call=None,
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

    def _assess_memories(
        self, scenario: AgentScenario, memories: list[Memory]
    ) -> list[MemoryAssessment]:
        assessments: list[MemoryAssessment] = []
        for memory in memories:
            supports_action = memory.benchmark_metadata.get(
                "supports_action", memory.benchmark_metadata.get("fake_action_bias")
            )
            if supports_action is not None and supports_action not in scenario.allowed_actions:
                raise ValueError(
                    f"invalid fake action bias {supports_action} for scenario {scenario.id}"
                )
            score, reasons = self._score_memory(memory)
            assessments.append(
                MemoryAssessment(
                    memory=memory,
                    supports_action=str(supports_action) if supports_action is not None else None,
                    score=score,
                    reasons=tuple(reasons),
                )
            )
        return assessments

    def _choose_action(self, scenario: AgentScenario, assessments: list[MemoryAssessment]) -> str:
        action_scores: dict[str, float] = defaultdict(float)
        interaction_groups: dict[str, list[str]] = defaultdict(list)

        for assessment in assessments:
            if assessment.supports_action is None:
                continue
            action_scores[assessment.supports_action] += assessment.score
            interaction_group = assessment.memory.benchmark_metadata.get("interaction_group")
            if interaction_group is not None:
                interaction_groups[str(interaction_group)].append(assessment.supports_action)

        for grouped_actions in interaction_groups.values():
            if len(grouped_actions) >= 2 and len(set(grouped_actions)) == 1:
                action_scores[grouped_actions[0]] += 5.0

        if action_scores:
            return max(
                scenario.allowed_actions,
                key=lambda action: (
                    action_scores.get(action, float("-inf")),
                    -scenario.allowed_actions.index(action),
                ),
            )

        fallback = scenario.evaluator_config.get("default_action", scenario.allowed_actions[0])
        if fallback not in scenario.allowed_actions:
            raise ValueError(f"invalid fallback action {fallback} for scenario {scenario.id}")
        return str(fallback)

    def _score_memory(self, memory: Memory) -> tuple[float, list[str]]:
        score = memory.retrieval_priority / 20
        reasons = [f"priority:{memory.retrieval_priority}"]

        status_weights = {
            "active": 2.0,
            "uncertain": -0.5,
            "stale": -2.5,
            "superseded": -3.0,
            "invalid": -4.0,
        }
        status_key = memory.status.value
        score += status_weights[status_key]
        reasons.append(f"status:{status_key}")

        role_weights = {
            "policy": 2.5,
            "approval": 2.0,
            "evidence": 2.0,
            "history": 0.5,
            "customer_status": 1.5,
            "inference": -2.0,
            "temporary": -1.0,
            "legacy_policy": -1.5,
        }
        memory_role = str(memory.operational_metadata.get("memory_role", "history"))
        score += role_weights.get(memory_role, 0.0)
        reasons.append(f"role:{memory_role}")

        score += (memory.confidence - 0.75) * 4
        reasons.append(f"confidence:{memory.confidence}")

        entity_match = bool(memory.operational_metadata.get("entity_match", True))
        score += 1.0 if entity_match else -3.0
        reasons.append(f"entity_match:{entity_match}")

        if memory.valid_until is not None and memory.valid_until < datetime.now(UTC):
            score -= 2.0
            reasons.append("expired")

        if memory.benchmark_metadata.get("should_ignore", False):
            score -= 3.0
            reasons.append("should_ignore")

        if self._is_superseded_by_current_memory(memory):
            score -= 2.5
            reasons.append("superseded_by_current_memory")

        salience_boost = float(memory.benchmark_metadata.get("salience_boost", 0.0))
        score += salience_boost
        if salience_boost > 0:
            reasons.append(f"salience_boost:{salience_boost}")

        return score, reasons

    def _is_superseded_by_current_memory(self, memory: Memory) -> bool:
        return memory.status.value in {"stale", "superseded"} and bool(
            memory.supersedes or memory.valid_until
        )
