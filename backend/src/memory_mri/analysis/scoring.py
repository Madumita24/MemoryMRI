from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

from memory_mri.analysis.models import (
    DeterministicPairObservation,
    DeterministicRelationship,
    DeterministicSignalObservation,
    DeterministicSuspicionResult,
    EvidenceStatusLabel,
    ReplayComparisonClassification,
    ReplayEvidenceSummary,
)
from memory_mri.config import SuspicionScoringConfig
from memory_mri.schemas import AgentInputMemory, ReplayResult


def build_deterministic_pair_observations(
    memories: list[AgentInputMemory],
) -> list[DeterministicPairObservation]:
    observations: list[DeterministicPairObservation] = []
    ordered = sorted(memories, key=lambda memory: memory.memory_id)
    for left, right in combinations(ordered, 2):
        observations.append(_analyze_pair(left, right))
    return observations


def score_memories(
    *,
    memories: list[AgentInputMemory],
    cited_memory_ids: list[str],
    pair_observations: list[DeterministicPairObservation],
    config: SuspicionScoringConfig,
) -> list[DeterministicSuspicionResult]:
    normalized_weights = config.normalized_signal_weights()
    superseded_targets = {
        superseded_id for memory in memories for superseded_id in memory.supersedes
    }
    pair_by_memory: dict[str, list[DeterministicPairObservation]] = defaultdict(list)
    for observation in pair_observations:
        pair_by_memory[observation.memory_a_id].append(observation)
        pair_by_memory[observation.memory_b_id].append(observation)

    results: list[DeterministicSuspicionResult] = []
    now = datetime.now(timezone.utc)
    for memory in memories:
        observations: list[DeterministicSignalObservation] = []
        memory_id = memory.memory_id

        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="cited_by_original_agent",
                present=memory_id in cited_memory_ids,
                normalized_weights=normalized_weights,
                reason=(
                    "The original agent cited this memory in its rationale."
                    if memory_id in cited_memory_ids
                    else "The original agent did not cite this memory."
                ),
            )
        )
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="stale_status",
                present=memory.status.value == "stale",
                normalized_weights=normalized_weights,
                reason=(
                    "The memory status is marked stale."
                    if memory.status.value == "stale"
                    else "The memory is not marked stale."
                ),
            )
        )
        expired = memory.valid_until is not None and memory.valid_until < now
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="expired_validity",
                present=expired,
                normalized_weights=normalized_weights,
                reason=(
                    "The memory validity window has already expired."
                    if expired
                    else "The memory validity window has not expired."
                ),
            )
        )
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="superseded_status",
                present=memory.status.value == "superseded",
                normalized_weights=normalized_weights,
                reason=(
                    "The memory status is marked superseded."
                    if memory.status.value == "superseded"
                    else "The memory is not marked superseded."
                ),
            )
        )
        entity_mismatch = memory.operational_metadata.get("entity_match") is False
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="entity_mismatch",
                present=entity_mismatch,
                normalized_weights=normalized_weights,
                reason=(
                    "Operational metadata marks this memory as an entity mismatch."
                    if entity_mismatch
                    else "Operational metadata does not mark an entity mismatch."
                ),
            )
        )
        missing_validity = memory.valid_from is None or memory.valid_until is None
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="missing_validity_dates",
                present=missing_validity,
                normalized_weights=normalized_weights,
                reason=(
                    "The memory is missing at least one validity boundary."
                    if missing_validity
                    else "The memory has both validity boundaries populated."
                ),
            )
        )
        high_priority = memory.retrieval_priority >= config.high_priority_threshold
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="unusually_high_retrieval_priority",
                present=high_priority,
                normalized_weights=normalized_weights,
                reason=(
                    f"The retrieval priority {memory.retrieval_priority} meets or exceeds "
                    f"the configured high-priority threshold "
                    f"{config.high_priority_threshold}."
                    if high_priority
                    else ("The retrieval priority is below the configured high-priority threshold.")
                ),
            )
        )
        metadata_conflict = any(
            observation.relationship
            in {
                DeterministicRelationship.CONTRADICTS,
                DeterministicRelationship.DUPLICATE,
                DeterministicRelationship.ENTITY_MISMATCH,
            }
            for observation in pair_by_memory[memory.memory_id]
        )
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="metadata_conflict_with_another_memory",
                present=metadata_conflict,
                normalized_weights=normalized_weights,
                reason=(
                    "Metadata checks found a conflict with another memory."
                    if metadata_conflict
                    else "Metadata checks did not find a conflict with another memory."
                ),
            )
        )
        wrong_context = (
            "wrong-context" in memory.tags
            or memory.operational_metadata.get("decision_context_match") is False
        )
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="potentially_wrong_decision_context",
                present=wrong_context,
                normalized_weights=normalized_weights,
                reason=(
                    "Metadata indicates the memory may be outside the current decision context."
                    if wrong_context
                    else (
                        "Metadata does not flag this memory as outside the current "
                        "decision context."
                    )
                ),
            )
        )
        invalid_temporal_overlap = any(
            observation.relationship == DeterministicRelationship.TEMPORAL_OVERLAP
            for observation in pair_by_memory[memory_id]
        )
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="invalid_temporal_overlap",
                present=invalid_temporal_overlap,
                normalized_weights=normalized_weights,
                reason=(
                    "A metadata-based temporal overlap concern exists with another memory."
                    if invalid_temporal_overlap
                    else "No metadata-based temporal overlap concern was detected."
                ),
            )
        )
        active_superseded = memory_id in superseded_targets and memory.status.value == "active"
        observations.append(
            _build_signal_observation(
                memory_id=memory_id,
                signal_name="active_memory_explicitly_superseded_by_another",
                present=active_superseded,
                normalized_weights=normalized_weights,
                reason=(
                    "Another memory explicitly supersedes this memory while it remains active."
                    if active_superseded
                    else "No active supersession signal is present."
                ),
            )
        )

        score = sum(observation.signal_contribution for observation in observations)
        results.append(
            DeterministicSuspicionResult(
                memory_id=memory.memory_id,
                metadata_observations=observations,
                deterministic_score=min(1.0, score),
            )
        )

    return results


def summarize_replay_evidence(
    *,
    memory_id: str,
    replay_results: list[ReplayResult],
    suspicion_score: float,
) -> tuple[ReplayEvidenceSummary, ReplayComparisonClassification]:
    matching_results = [
        result for result in replay_results if result.intervention.target_memory_ids == [memory_id]
    ]
    if not matching_results:
        summary = ReplayEvidenceSummary(
            replay_evidence_available=False,
            replay_run_count=0,
            infrastructure_error_count=0,
            evidence_status_label=(
                EvidenceStatusLabel.METADATA_CONCERN
                if suspicion_score > 0
                else EvidenceStatusLabel.HYPOTHESIS_ONLY
            ),
        )
        return summary, ReplayComparisonClassification.NOT_REPLAY_TESTED

    strongest_result = max(matching_results, key=lambda result: abs(result.influence_delta))
    observed_action_change = any(
        result.original_action_distribution != result.intervention_action_distribution
        for result in matching_results
    )
    infrastructure_errors = sum(
        len(result.original_errors) + len(result.intervention_errors) for result in matching_results
    )
    if infrastructure_errors > 0 and all(result.total_runs == 0 for result in matching_results):
        status = EvidenceStatusLabel.REPLAY_INCONCLUSIVE
        comparison = ReplayComparisonClassification.INCONCLUSIVE
    else:
        influence = abs(strongest_result.influence_delta)
        if influence < 0.01 and not observed_action_change:
            status = EvidenceStatusLabel.REPLAY_TESTED_NO_OBSERVED_INFLUENCE
        elif influence < 0.2:
            status = EvidenceStatusLabel.REPLAY_TESTED_WEAK_OBSERVED_INFLUENCE
        elif influence < 0.5:
            status = EvidenceStatusLabel.REPLAY_TESTED_MODERATE_OBSERVED_INFLUENCE
        else:
            status = EvidenceStatusLabel.REPLAY_TESTED_STRONG_OBSERVED_INFLUENCE

        if suspicion_score >= 0.5 and (influence >= 0.2 or observed_action_change):
            comparison = ReplayComparisonClassification.SUPPORTED_BY_REPLAY
        elif suspicion_score >= 0.5:
            comparison = ReplayComparisonClassification.NOT_SUPPORTED_BY_REPLAY
        elif influence >= 0.2 or observed_action_change:
            comparison = ReplayComparisonClassification.LOW_SUSPICION_BUT_EFFECT_OBSERVED
        else:
            comparison = ReplayComparisonClassification.NOT_SUPPORTED_BY_REPLAY

    return (
        ReplayEvidenceSummary(
            replay_evidence_available=True,
            observed_individual_influence=strongest_result.influence_delta,
            observed_action_change=observed_action_change,
            intervention_success_rate=strongest_result.success_rate,
            replay_run_count=strongest_result.total_runs,
            wilson_interval_low=strongest_result.confidence_interval_low,
            wilson_interval_high=strongest_result.confidence_interval_high,
            replay_stability=strongest_result.intervention_replay_stability,
            infrastructure_error_count=infrastructure_errors,
            evidence_status_label=status,
        ),
        comparison,
    )


def _analyze_pair(left: AgentInputMemory, right: AgentInputMemory) -> DeterministicPairObservation:
    if right.memory_id in left.supersedes or left.memory_id in right.supersedes:
        superseding_id = left.memory_id if right.memory_id in left.supersedes else right.memory_id
        superseded_id = right.memory_id if right.memory_id in left.supersedes else left.memory_id
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.SUPERSEDES,
            concise_reason=(f"{superseding_id} explicitly supersedes {superseded_id} in metadata."),
            relevant_fields=["supersedes", "status"],
            confidence=1.0,
        )

    duplicate_group_left = left.operational_metadata.get("duplicate_group")
    duplicate_group_right = right.operational_metadata.get("duplicate_group")
    if duplicate_group_left and duplicate_group_left == duplicate_group_right:
        left_value = left.operational_metadata.get("attribute_value")
        right_value = right.operational_metadata.get("attribute_value")
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.DUPLICATE,
            concise_reason=(
                "The memories share a duplicate-group marker, and metadata should be checked "
                "for inconsistent values."
            ),
            relevant_fields=["duplicate_group", "attribute_value"],
            confidence=0.9 if left_value != right_value else 0.7,
        )

    same_attribute = bool(
        left.operational_metadata.get("attribute_key")
    ) and left.operational_metadata.get("attribute_key") == right.operational_metadata.get(
        "attribute_key"
    )
    if same_attribute and left.entity_id == right.entity_id:
        left_value = left.operational_metadata.get("attribute_value")
        right_value = right.operational_metadata.get("attribute_value")
        if left_value is not None and right_value is not None and left_value != right_value:
            return DeterministicPairObservation(
                memory_a_id=left.memory_id,
                memory_b_id=right.memory_id,
                relationship=DeterministicRelationship.CONTRADICTS,
                concise_reason=(
                    "Metadata assigns different values to the same entity and attribute."
                ),
                relevant_fields=["entity_id", "attribute_key", "attribute_value"],
                confidence=0.95,
            )

    if (
        left.operational_metadata.get("entity_match") is False
        or right.operational_metadata.get("entity_match") is False
    ):
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.ENTITY_MISMATCH,
            concise_reason="At least one memory is explicitly marked as an entity mismatch.",
            relevant_fields=["entity_match", "entity_id"],
            confidence=0.9,
        )

    if _has_invalid_temporal_overlap(left, right):
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.TEMPORAL_OVERLAP,
            concise_reason=("The memories overlap in time with incompatible attribute metadata."),
            relevant_fields=["valid_from", "valid_until", "attribute_key", "attribute_value"],
            confidence=0.85,
        )

    if _related_policy_records_without_precedence(left, right):
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.POTENTIALLY_CONSISTENT,
            concise_reason=(
                "The memories appear policy-related but lack explicit precedence metadata."
            ),
            relevant_fields=["memory_role", "temporal_scope", "supersedes"],
            confidence=0.55,
        )

    if left.entity_id == right.entity_id or (
        left.operational_metadata.get("memory_role")
        == right.operational_metadata.get("memory_role")
    ):
        return DeterministicPairObservation(
            memory_a_id=left.memory_id,
            memory_b_id=right.memory_id,
            relationship=DeterministicRelationship.POTENTIALLY_CONSISTENT,
            concise_reason="Metadata suggests the memories may be relevant to the same decision.",
            relevant_fields=["entity_id", "memory_role"],
            confidence=0.5,
        )

    return DeterministicPairObservation(
        memory_a_id=left.memory_id,
        memory_b_id=right.memory_id,
        relationship=DeterministicRelationship.UNRELATED,
        concise_reason="Metadata does not show a direct relationship between the memories.",
        relevant_fields=[],
        confidence=0.6,
    )


def _has_invalid_temporal_overlap(left: AgentInputMemory, right: AgentInputMemory) -> bool:
    if left.valid_from is None or right.valid_from is None:
        return False
    left_end = left.valid_until or datetime.max.replace(tzinfo=timezone.utc)
    right_end = right.valid_until or datetime.max.replace(tzinfo=timezone.utc)
    overlaps = left.valid_from <= right_end and right.valid_from <= left_end
    same_attribute = bool(
        left.operational_metadata.get("attribute_key")
    ) and left.operational_metadata.get("attribute_key") == right.operational_metadata.get(
        "attribute_key"
    )
    different_value = (
        left.operational_metadata.get("attribute_value") is not None
        and right.operational_metadata.get("attribute_value") is not None
        and left.operational_metadata.get("attribute_value")
        != right.operational_metadata.get("attribute_value")
    )
    return overlaps and same_attribute and different_value


def _related_policy_records_without_precedence(
    left: AgentInputMemory, right: AgentInputMemory
) -> bool:
    left_role = str(left.operational_metadata.get("memory_role", ""))
    right_role = str(right.operational_metadata.get("memory_role", ""))
    policy_like = {"policy", "legacy_policy", "policy_history"}
    return bool(
        left_role in policy_like
        and right_role in policy_like
        and not left.supersedes
        and not right.supersedes
    )


def _build_signal_observation(
    *,
    memory_id: str,
    signal_name: str,
    present: bool,
    normalized_weights: dict[str, float],
    reason: str,
) -> DeterministicSignalObservation:
    return DeterministicSignalObservation(
        memory_id=memory_id,
        signal_name=signal_name,
        signal_present=present,
        signal_contribution=normalized_weights[signal_name] if present else 0.0,
        concise_reason=reason,
    )
