from __future__ import annotations

from datetime import datetime
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


class InterventionType(StrEnum):
    REMOVE_MEMORY = "REMOVE_MEMORY"
    DISABLE_MEMORY = "DISABLE_MEMORY"
    LOWER_RETRIEVAL_PRIORITY = "LOWER_RETRIEVAL_PRIORITY"
    MARK_SUPERSEDED = "MARK_SUPERSEDED"
    REPLACE_MEMORY_WITH_CANDIDATE = "REPLACE_MEMORY_WITH_CANDIDATE"


class ReplayMode(StrEnum):
    FAST = "fast"
    DEEP = "deep"
    CUSTOM = "custom"


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


class RepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    scenario_id: str
    repair_type: str
    target_memory_ids: list[str]
    before: dict[str, Any]
    after: dict[str, Any]
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: bool = True
    status: RepairStatus = RepairStatus.PROPOSED


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
