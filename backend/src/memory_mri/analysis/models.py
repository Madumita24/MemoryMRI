from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_mri.domain.actions import DomainName
from memory_mri.schemas import AgentInputMemory


class SuspicionIssueType(StrEnum):
    STALE = "stale"
    CONTRADICTORY = "contradictory"
    SUPERSEDED = "superseded"
    WRONG_ENTITY = "wrong_entity"
    WRONG_CONTEXT = "wrong_context"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    EXCESSIVE_PRIORITY = "excessive_priority"
    MISSING_VALIDITY = "missing_validity"
    NONE = "none"


class EvidenceStatusLabel(StrEnum):
    HYPOTHESIS_ONLY = "hypothesis only"
    METADATA_CONCERN = "metadata concern"
    REPLAY_TESTED_NO_OBSERVED_INFLUENCE = "replay tested: no observed influence"
    REPLAY_TESTED_WEAK_OBSERVED_INFLUENCE = "replay tested: weak observed influence"
    REPLAY_TESTED_MODERATE_OBSERVED_INFLUENCE = "replay tested: moderate observed influence"
    REPLAY_TESTED_STRONG_OBSERVED_INFLUENCE = "replay tested: strong observed influence"
    REPLAY_INCONCLUSIVE = "replay inconclusive"


class ReplayComparisonClassification(StrEnum):
    SUPPORTED_BY_REPLAY = "suspicion supported by replay"
    NOT_SUPPORTED_BY_REPLAY = "suspicion not supported by replay"
    LOW_SUSPICION_BUT_EFFECT_OBSERVED = "low suspicion but replay effect observed"
    NOT_REPLAY_TESTED = "not replay tested"
    INCONCLUSIVE = "inconclusive"


class DeterministicRelationship(StrEnum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DUPLICATE = "duplicate"
    TEMPORAL_OVERLAP = "temporal_overlap"
    ENTITY_MISMATCH = "entity_mismatch"
    POTENTIALLY_CONSISTENT = "potentially_consistent"
    UNRELATED = "unrelated"


class DeterministicSignalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    signal_name: str
    signal_present: bool
    signal_contribution: float = Field(ge=0.0, le=1.0)
    concise_reason: str


class DeterministicSuspicionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    metadata_observations: list[DeterministicSignalObservation]
    deterministic_score: float = Field(ge=0.0, le=1.0)


class SemanticMemoryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    semantic_suspicion_score: float = Field(ge=0.0, le=1.0)
    suspected_issue_types: list[SuspicionIssueType]
    concise_reason: str = Field(min_length=1, max_length=280)
    related_memory_ids: list[str] = Field(default_factory=list)
    uncertainty: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool

    @field_validator("related_memory_ids")
    @classmethod
    def unique_related_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("related_memory_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_issue_types(self) -> "SemanticMemoryAnalysis":
        if not self.suspected_issue_types:
            raise ValueError("suspected_issue_types must not be empty")
        if (
            SuspicionIssueType.NONE in self.suspected_issue_types
            and len(self.suspected_issue_types) > 1
        ):
            raise ValueError("'none' cannot be combined with other issue types")
        return self


class SemanticMemoryAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyses: list[SemanticMemoryAnalysis]


class ReplayEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_evidence_available: bool
    observed_individual_influence: float | None = None
    observed_action_change: bool | None = None
    intervention_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    replay_run_count: int = Field(ge=0)
    wilson_interval_low: float | None = Field(default=None, ge=0.0, le=1.0)
    wilson_interval_high: float | None = Field(default=None, ge=0.0, le=1.0)
    replay_stability: float | None = Field(default=None, ge=0.0, le=1.0)
    infrastructure_error_count: int = Field(ge=0)
    evidence_status_label: EvidenceStatusLabel


class MemoryPriorityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    deterministic_score: float = Field(ge=0.0, le=1.0)
    semantic_score: float = Field(ge=0.0, le=1.0)
    prioritization_score: float = Field(ge=0.0, le=1.0)
    metadata_observations: list[DeterministicSignalObservation]
    semantic_hypothesis: SemanticMemoryAnalysis
    replay_supported_evidence: ReplayEvidenceSummary
    comparison_classification: ReplayComparisonClassification
    deterministic_reasons: list[str] = Field(default_factory=list)
    semantic_reason: str


class AnalysisArtifactMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    domain: DomainName
    model: str
    response_model: str
    semantic_analysis_prompt_version: str
    semantic_analysis_prompt_hash: str
    memory_snapshot_hash: str
    deterministic_score_configuration: dict[str, Any]
    created_at: datetime
    api_usage: dict[str, int]
    git_commit_hash: str


class InvestigationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_ranked_memories: list[str]
    deterministic_concerns: list[str]
    semantic_concerns: list[str]
    contradictions_detected: list[str]
    replay_supported_memories: list[str]
    suspicious_memories_with_no_observed_influence: list[str]
    pairwise_testing_recommended: bool
    no_memory_or_prompt_only_testing_recommended: bool
    human_review_recommended: bool


class SuspicionRankingArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: AnalysisArtifactMetadata
    memories: list[MemoryPriorityResult]
    summary: InvestigationSummary


class DeterministicPairObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_a_id: str
    memory_b_id: str
    relationship: DeterministicRelationship
    evidence_type: Literal["metadata"] = "metadata"
    concise_reason: str
    relevant_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class SemanticPairAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_a_id: str
    memory_b_id: str
    relationship: DeterministicRelationship
    concise_explanation: str = Field(min_length=1, max_length=280)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool


class SemanticPairAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairs: list[SemanticPairAnalysis]


class PairAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_a_id: str
    memory_b_id: str
    deterministic_relationship: DeterministicPairObservation
    semantic_relationship: SemanticPairAnalysis
    relationships_agree: bool
    replay_evidence_exists_for_either: bool
    pairwise_replay_performed: bool


class ContradictionAnalysisArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: AnalysisArtifactMetadata
    pair_results: list[PairAnalysisResult]
    summary: InvestigationSummary


class SuspicionAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    domain: DomainName
    user_request: str
    allowed_actions: list[str]
    original_selected_action: str | None = None
    concise_original_rationale: str | None = None
    memories: list[AgentInputMemory]


class ContradictionPairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_a_id: str
    memory_b_id: str


class ContradictionAnalysisInput(SuspicionAnalysisInput):
    pairs: list[ContradictionPairInput]
