from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_mri.domain.actions import DOMAIN_ACTIONS, DomainName

AGENT_INPUT_SCHEMA_VERSION = "day2a-v1"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    UNCERTAIN = "uncertain"
    INVALID = "invalid"


class RepairStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    REVERTED = "reverted"


class MemoryVersionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVERTED = "reverted"


class AuditEventType(StrEnum):
    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    PROPOSAL_APPLIED = "proposal_applied"
    PROPOSAL_REVERTED = "proposal_reverted"
    FAILED_TRANSITION = "failed_transition"


class RepairType(StrEnum):
    INVALIDATE_MEMORY = "INVALIDATE_MEMORY"
    ADD_EXPIRATION_DATE = "ADD_EXPIRATION_DATE"
    MARK_SUPERSEDED = "MARK_SUPERSEDED"
    CORRECT_ENTITY_ASSOCIATION = "CORRECT_ENTITY_ASSOCIATION"
    MERGE_CONTRADICTORY_MEMORIES = "MERGE_CONTRADICTORY_MEMORIES"
    LOWER_RETRIEVAL_PRIORITY = "LOWER_RETRIEVAL_PRIORITY"
    REQUIRE_HUMAN_CONFIRMATION = "REQUIRE_HUMAN_CONFIRMATION"
    REPLACE_WITH_CORRECTED_FACT = "REPLACE_WITH_CORRECTED_FACT"
    ADD_CONTEXT_CONSTRAINT = "ADD_CONTEXT_CONSTRAINT"
    ADD_PRECEDENCE_METADATA = "ADD_PRECEDENCE_METADATA"
    NO_MEMORY_REPAIR_RECOMMENDED = "NO_MEMORY_REPAIR_RECOMMENDED"
    ESCALATE_PROMPT_OR_POLICY_REVIEW = "ESCALATE_PROMPT_OR_POLICY_REVIEW"


class InterventionType(StrEnum):
    REMOVE_MEMORY = "REMOVE_MEMORY"
    DISABLE_MEMORY = "DISABLE_MEMORY"
    REMOVE_MEMORIES = "REMOVE_MEMORIES"
    DISABLE_MEMORIES = "DISABLE_MEMORIES"
    REMOVE_ALL_MEMORIES = "REMOVE_ALL_MEMORIES"
    ISOLATE_MEMORY = "ISOLATE_MEMORY"
    LOWER_RETRIEVAL_PRIORITY = "LOWER_RETRIEVAL_PRIORITY"
    MARK_SUPERSEDED = "MARK_SUPERSEDED"
    REPLACE_MEMORY_WITH_CANDIDATE = "REPLACE_MEMORY_WITH_CANDIDATE"


class ReplayMode(StrEnum):
    FAST = "fast"
    DEEP = "deep"
    CUSTOM = "custom"


class MemoryDependenceClassification(StrEnum):
    INDIVIDUAL_MEMORY_DEPENDENT = "individual-memory dependent"
    PAIRWISE_MEMORY_DEPENDENT = "pairwise-memory dependent"
    DISTRIBUTED_MEMORY_DEPENDENT = "distributed-memory dependent"
    LIKELY_MEMORY_INDEPENDENT = "likely memory-independent"
    INCONCLUSIVE = "inconclusive"


class PairEvidenceClassification(StrEnum):
    INTERACTION_SUPPORTED = "interaction-supported"
    DOMINATED_BY_ONE_MEMORY = "dominated by one memory"
    REDUNDANT_PAIR = "redundant pair"
    NEGATIVE_INTERACTION = "negative interaction"
    NO_OBSERVED_PAIRWISE_INFLUENCE = "no observed pairwise influence"
    INCONCLUSIVE = "inconclusive"


class Memory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    domain: DomainName
    content: str
    source: str
    created_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    status: MemoryStatus
    supersedes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    retrieval_priority: int = Field(ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    operational_metadata: dict[str, Any] = Field(default_factory=dict)
    benchmark_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "Memory":
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from")
        return self

    def to_agent_input(self) -> "AgentInputMemory":
        return AgentInputMemory(
            memory_id=self.id,
            entity_id=self.entity_id,
            content=self.content,
            source=self.source,
            created_at=self.created_at,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            status=self.status,
            confidence=self.confidence,
            retrieval_priority=self.retrieval_priority,
            supersedes=self.supersedes,
            tags=self.tags,
            operational_metadata=self.operational_metadata,
        )


class AgentScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    domain: DomainName
    user_input: str
    allowed_actions: list[str]
    expected_action: str
    memory_ids: list[str] = Field(min_length=1)
    expected_problematic_memory_ids: list[str] = Field(default_factory=list)
    failure_category: str
    explanation: str
    evaluator_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_actions")
    @classmethod
    def validate_allowed_actions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_actions must be unique")
        return value

    @model_validator(mode="after")
    def validate_action_membership(self) -> "AgentScenario":
        known_actions = set(DOMAIN_ACTIONS[self.domain])
        if any(action not in known_actions for action in self.allowed_actions):
            raise ValueError("allowed_actions contain unsupported action for domain")
        if self.expected_action not in self.allowed_actions:
            raise ValueError("expected_action must be in allowed_actions")
        missing_memory_ids = set(self.expected_problematic_memory_ids) - set(self.memory_ids)
        if missing_memory_ids:
            raise ValueError("expected_problematic_memory_ids must exist in memory_ids")
        return self

    def to_agent_input(self, memories: list[Memory]) -> "AgentInput":
        scenario_memories = [memory for memory in memories if memory.id in self.memory_ids]
        return build_agent_input(self, scenario_memories)


class AgentInputMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    entity_id: str
    content: str
    source: str
    created_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    status: MemoryStatus
    confidence: float = Field(ge=0.0, le=1.0)
    retrieval_priority: int = Field(ge=0, le=100)
    supersedes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    operational_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = AGENT_INPUT_SCHEMA_VERSION
    scenario_id: str
    domain: DomainName
    user_input: str
    allowed_actions: list[str]
    memories: list[AgentInputMemory]


class EvaluatorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_action: str
    selected_action: str
    passed: bool
    reason: str


class StructuredAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_action: str
    action_arguments: dict[str, Any] = Field(default_factory=dict)
    cited_memory_ids: list[str] = Field(default_factory=list)
    concise_rationale: str
    uncertainty: float = Field(ge=0.0, le=1.0)
    needs_human_review: bool


class TraceEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator_result: EvaluatorResult | None = None


class TraceCacheStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    request_hash: str | None = None
    hit: bool | None = None
    cache_path: str | None = None
    cached_at: datetime | None = None


class TraceErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    attempts: int


class ExecutionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    scenario_id: str
    run_id: str
    domain: DomainName
    user_input: str
    agent_input: AgentInput
    requested_model: str
    response_model: str
    model: str
    prompt_version: str
    prompt_content_hash: str | None = None
    agent_input_schema_version: str = AGENT_INPUT_SCHEMA_VERSION
    request_hash: str | None = None
    retrieved_memory_ids: list[str]
    memory_snapshot: list[AgentInputMemory]
    structured_response: StructuredAgentResponse | None = None
    selected_action: str | None = None
    action_arguments: dict[str, Any] = Field(default_factory=dict)
    cited_memory_ids: list[str] = Field(default_factory=list)
    concise_rationale: str | None = None
    uncertainty: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_human_review: bool | None = None
    tool_call: dict[str, Any] | None = None
    evaluation: TraceEvaluation = Field(default_factory=TraceEvaluation)
    passed: bool | None = None
    execution_source: str = "live"
    cache_lookup_latency_ms: int | None = Field(default=None, ge=0)
    original_model_latency_ms: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    request_token_usage: dict[str, int] | None = None
    cached_original_token_usage: dict[str, int] | None = None
    billable_api_call: bool = False
    cache: TraceCacheStatus = Field(default_factory=lambda: TraceCacheStatus(enabled=False))
    parent_trace_id: str | None = None
    investigation_id: str | None = None
    replay_intervention: Intervention | None = None
    replay_role: str | None = None
    error: TraceErrorDetails | None = None
    created_at: datetime


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    selected_action: str
    expected_action: str
    passed: bool
    retrieved_memory_ids: list[str]
    trace_id: str
    error: str | None = None


class Intervention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intervention_type: InterventionType
    target_memory_ids: list[str]
    replacement_values: dict[str, Any] = Field(default_factory=dict)
    reason: str
    intervention_id: str = Field(default_factory=lambda: f"intervention_{uuid4().hex}")
    before_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    after_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    unchanged_input_hash: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    inference_configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    intervention: Intervention
    mode: ReplayMode
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    confidence_interval_low: float = Field(ge=0.0, le=1.0)
    confidence_interval_high: float = Field(ge=0.0, le=1.0)
    original_successful_runs: int = Field(ge=0)
    original_total_runs: int = Field(ge=0)
    original_success_rate: float = Field(ge=0.0, le=1.0)
    influence_delta: float
    original_action_distribution: dict[str, int] = Field(default_factory=dict)
    intervention_action_distribution: dict[str, int] = Field(default_factory=dict)
    original_replay_stability: float = Field(ge=0.0, le=1.0)
    intervention_replay_stability: float = Field(ge=0.0, le=1.0)
    original_errors: list[TraceErrorDetails] = Field(default_factory=list)
    intervention_errors: list[TraceErrorDetails] = Field(default_factory=list)
    original_trace_ids: list[str] = Field(default_factory=list)
    intervention_trace_ids: list[str] = Field(default_factory=list)


class Investigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    domain: DomainName
    requested_model: str
    response_model: str
    prompt_version: str
    prompt_content_hash: str | None = None
    run_count: int = Field(ge=1)
    mode: ReplayMode
    cache_policy: str
    original_selected_action: str | None = None
    expected_action: str
    original_memory_snapshot: list[AgentInputMemory]
    replay_results: list[ReplayResult] = Field(default_factory=list)
    created_at: datetime


class DecisionSupportAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_correct: bool
    decision_still_supported: bool
    support_explanation: str
    requires_human_review: bool


class PairSelectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_memory_ids: list[str]
    generated_pairs: list[list[str]]
    ranking_source: str
    ranking_version: str | None = None
    ranking_snapshot_hash: str | None = None
    created_at: datetime


class PairwiseReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    intervention: Intervention
    shared_baseline_runs: bool
    fresh_baseline_per_pair: bool
    original_successful_runs: int = Field(ge=0)
    original_total_evaluated_runs: int = Field(ge=0)
    original_success_rate: float = Field(ge=0.0, le=1.0)
    original_action_distribution: dict[str, int] = Field(default_factory=dict)
    individual_influences: dict[str, float] = Field(default_factory=dict)
    combined_successful_runs: int = Field(ge=0)
    combined_total_evaluated_runs: int = Field(ge=0)
    combined_success_rate: float = Field(ge=0.0, le=1.0)
    combined_action_distribution: dict[str, int] = Field(default_factory=dict)
    combined_influence: float
    interaction_score: float
    interaction_synergy: float
    confidence_interval_low: float = Field(ge=0.0, le=1.0)
    confidence_interval_high: float = Field(ge=0.0, le=1.0)
    replay_stability: float = Field(ge=0.0, le=1.0)
    infrastructure_error_count: int = Field(ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    support_validity: DecisionSupportAudit
    evidence_classification: PairEvidenceClassification
    original_trace_ids: list[str] = Field(default_factory=list)
    intervention_trace_ids: list[str] = Field(default_factory=list)


class MemoryControlType(StrEnum):
    NO_MEMORY = "no-memory"
    ISOLATE_MEMORY = "isolate-memory"


class MemoryControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    control_type: MemoryControlType
    target_memory_id: str | None = None
    intervention: Intervention
    original_successful_runs: int = Field(ge=0)
    original_total_evaluated_runs: int = Field(ge=0)
    original_success_rate: float = Field(ge=0.0, le=1.0)
    original_action_distribution: dict[str, int] = Field(default_factory=dict)
    control_successful_runs: int = Field(ge=0)
    control_total_evaluated_runs: int = Field(ge=0)
    control_success_rate: float = Field(ge=0.0, le=1.0)
    control_action_distribution: dict[str, int] = Field(default_factory=dict)
    replay_stability: float = Field(ge=0.0, le=1.0)
    infrastructure_error_count: int = Field(ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0)
    support_validity: DecisionSupportAudit
    original_trace_ids: list[str] = Field(default_factory=list)
    control_trace_ids: list[str] = Field(default_factory=list)


class PairwiseReplayArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    original_snapshot_hash: str
    pair_selection: PairSelectionRecord
    shared_baseline_runs: bool
    fresh_baseline_per_pair: bool
    individual_replay_evidence: list[ReplayResult]
    pair_results: list[PairwiseReplayResult]
    memory_dependence_classification: MemoryDependenceClassification
    model: str
    prompt_version: str
    api_usage: dict[str, int] = Field(default_factory=dict)
    git_commit_hash: str
    created_at: datetime


class MemoryControlsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    original_snapshot_hash: str
    no_memory_control: MemoryControlResult
    isolation_controls: list[MemoryControlResult]
    memory_dependence_classification: MemoryDependenceClassification
    model: str
    prompt_version: str
    api_usage: dict[str, int] = Field(default_factory=dict)
    git_commit_hash: str
    created_at: datetime


class ProposalEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_trace_id: str
    replay_artifact_ids: list[str] = Field(default_factory=list)
    contradiction_artifact_ids: list[str] = Field(default_factory=list)
    memory_snapshot_hash: str
    git_commit_hash: str
    prompt_hash: str | None = None


class ProposalReplayEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_evidence_exists: bool
    behavior_change_observed: bool
    memory_dependent_failure: bool
    no_memory_control_preserved_wrong_action: bool
    strongest_intervention_type: str | None = None
    strongest_target_memory_ids: list[str] = Field(default_factory=list)
    strongest_influence_delta: float | None = None
    strongest_action_distribution: dict[str, int] = Field(default_factory=dict)
    support_explanation: str
    evidence_references: ProposalEvidenceReference


class ProposalSuspicionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_ranked_memory_ids: list[str] = Field(default_factory=list)
    replay_supported_memory_ids: list[str] = Field(default_factory=list)
    suspicious_without_observed_influence: list[str] = Field(default_factory=list)
    semantic_hypotheses: list[str] = Field(default_factory=list)
    evidence_references: ProposalEvidenceReference


class ProposalContradictionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_pairs: list[str] = Field(default_factory=list)
    contradictory_target_memory_ids: list[str] = Field(default_factory=list)
    semantic_findings: list[str] = Field(default_factory=list)
    evidence_references: ProposalEvidenceReference


class SupportValidityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_still_supported: bool
    outcome_correct: bool
    requires_human_review: bool
    support_explanation: str


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    approver_id: str = "local_user"
    approval_reason: str = Field(min_length=1, max_length=400)
    approved_at: datetime
    evidence_reviewed: list[str] = Field(default_factory=list)
    acknowledged_risks: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=400)


class RejectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    actor_id: str = "local_user"
    rejection_reason: str = Field(min_length=1, max_length=400)
    rejected_at: datetime
    notes: str | None = Field(default=None, max_length=400)


class MemoryStoreVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str
    parent_version_id: str | None = None
    investigation_id: str
    proposal_id: str | None = None
    scenario_id: str
    created_at: datetime
    created_by: str
    memory_snapshot: list[AgentInputMemory]
    snapshot_hash: str
    change_summary: str
    status: MemoryVersionStatus


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    investigation_id: str
    proposal_id: str | None = None
    scenario_id: str
    event_type: AuditEventType
    actor: str
    timestamp: datetime
    status_from: RepairStatus | None = None
    status_to: RepairStatus | None = None
    snapshot_hash: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    investigation_id: str
    scenario_id: str
    domain: DomainName
    repair_type: RepairType
    target_memory_ids: list[str] = Field(default_factory=list)
    before_state: dict[str, Any]
    proposed_after_state: dict[str, Any]
    replay_evidence: ProposalReplayEvidence
    suspicion_evidence: ProposalSuspicionEvidence
    contradiction_evidence: ProposalContradictionEvidence
    support_validity_result: SupportValidityResult
    expected_affected_scenarios: list[str] = Field(default_factory=list)
    expected_behavior_change: str = Field(min_length=1, max_length=400)
    risks: list[str] = Field(min_length=1)
    rollback_plan: str = Field(min_length=1, max_length=400)
    concise_explanation: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: bool = True
    proposal_status: RepairStatus = RepairStatus.PROPOSED
    model: str
    prompt_version: str
    created_at: datetime
    evidence_references: ProposalEvidenceReference
    approval_record: ApprovalRecord | None = None
    rejection_record: RejectionRecord | None = None
    applied_version_id: str | None = None
    reverted_version_id: str | None = None

    @field_validator("target_memory_ids", "expected_affected_scenarios")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value


class VerificationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    scenario_id: str
    original_failure: ScenarioResult
    suspected_memories: list[str]
    replay_evidence: list[ReplayResult]
    approved_repair: RepairProposal | None = None
    original_case_after_repair: ScenarioResult | None = None
    domain_regression_results: dict[str, Any] = Field(default_factory=dict)
    complete_benchmark_results: dict[str, Any] = Field(default_factory=dict)
    unrelated_behavior_changes: list[str] = Field(default_factory=list)
    created_at: datetime


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: AgentScenario
    memories: list[Memory] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_memory_refs(self) -> "BenchmarkCase":
        memory_ids = {memory.id for memory in self.memories}
        missing = set(self.scenario.memory_ids) - memory_ids
        if missing:
            raise ValueError("scenario memory_ids must resolve to supplied memories")
        return self


class BenchmarkDomainFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainName
    cases: list[BenchmarkCase]

    @model_validator(mode="after")
    def validate_case_domains(self) -> "BenchmarkDomainFile":
        for case in self.cases:
            if case.scenario.domain != self.domain:
                raise ValueError("scenario domain must match file domain")
            if any(memory.domain != self.domain for memory in case.memories):
                raise ValueError("memory domain must match file domain")
        return self


def new_trace_id() -> str:
    return f"trace_{uuid4().hex}"


def new_run_id() -> str:
    return f"run_{uuid4().hex}"


def build_agent_input(scenario: AgentScenario, memories: list[Memory]) -> AgentInput:
    memory_lookup = {memory.id: memory for memory in memories}
    # The prompt consumes memories in scenario.memory_ids order, so we normalize
    # to that canonical order before serialization and request hashing.
    ordered_memories = [
        memory_lookup[memory_id] for memory_id in scenario.memory_ids if memory_id in memory_lookup
    ]
    return AgentInput(
        schema_version=AGENT_INPUT_SCHEMA_VERSION,
        scenario_id=scenario.id,
        domain=scenario.domain,
        user_input=scenario.user_input,
        allowed_actions=scenario.allowed_actions,
        memories=[memory.to_agent_input() for memory in ordered_memories],
    )
