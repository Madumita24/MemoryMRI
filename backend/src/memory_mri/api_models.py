from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from memory_mri.analysis.models import ContradictionAnalysisArtifact, SuspicionRankingArtifact
from memory_mri.domain.actions import DomainName
from memory_mri.schemas import (
    AgentInput,
    AgentInputMemory,
    ExecutionTrace,
    Investigation,
    MemoryControlsArtifact,
    PairwiseReplayArtifact,
    ReplayMode,
    ReplayResult,
    StructuredAgentResponse,
    TraceCacheStatus,
    TraceErrorDetails,
)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class DomainInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainName
    allowed_actions: list[str]


class PublicScenarioSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    domain: DomainName
    allowed_actions: list[str]
    memory_count: int = Field(ge=0)


class PublicScenarioDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    title: str
    domain: DomainName
    user_input: str
    allowed_actions: list[str]
    memory_ids: list[str]
    agent_input: AgentInput


class PublicTrace(BaseModel):
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
    retrieved_memory_ids: list[str]
    memory_snapshot: list[AgentInputMemory]
    structured_response: StructuredAgentResponse | None = None
    selected_action: str | None = None
    action_arguments: dict[str, Any] = Field(default_factory=dict)
    cited_memory_ids: list[str] = Field(default_factory=list)
    concise_rationale: str | None = None
    uncertainty: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_human_review: bool | None = None
    passed: bool | None = None
    execution_source: str
    cache_lookup_latency_ms: int | None = Field(default=None, ge=0)
    original_model_latency_ms: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    token_usage: dict[str, int] = Field(default_factory=dict)
    request_token_usage: dict[str, int] | None = None
    cached_original_token_usage: dict[str, int] | None = None
    billable_api_call: bool = False
    cache: TraceCacheStatus
    parent_trace_id: str | None = None
    investigation_id: str | None = None
    replay_role: str | None = None
    error: TraceErrorDetails | None = None
    created_at: datetime

    @classmethod
    def from_trace(cls, trace: ExecutionTrace) -> "PublicTrace":
        return cls(
            trace_id=trace.trace_id,
            scenario_id=trace.scenario_id,
            run_id=trace.run_id,
            domain=trace.domain,
            user_input=trace.user_input,
            agent_input=trace.agent_input,
            requested_model=trace.requested_model,
            response_model=trace.response_model,
            model=trace.model,
            prompt_version=trace.prompt_version,
            retrieved_memory_ids=trace.retrieved_memory_ids,
            memory_snapshot=trace.memory_snapshot,
            structured_response=trace.structured_response,
            selected_action=trace.selected_action,
            action_arguments=trace.action_arguments,
            cited_memory_ids=trace.cited_memory_ids,
            concise_rationale=trace.concise_rationale,
            uncertainty=trace.uncertainty,
            needs_human_review=trace.needs_human_review,
            passed=trace.passed,
            execution_source=trace.execution_source,
            cache_lookup_latency_ms=trace.cache_lookup_latency_ms,
            original_model_latency_ms=trace.original_model_latency_ms,
            latency_ms=trace.latency_ms,
            token_usage=trace.token_usage,
            request_token_usage=trace.request_token_usage,
            cached_original_token_usage=trace.cached_original_token_usage,
            billable_api_call=trace.billable_api_call,
            cache=trace.cache,
            parent_trace_id=trace.parent_trace_id,
            investigation_id=trace.investigation_id,
            replay_role=trace.replay_role,
            error=trace.error,
            created_at=trace.created_at,
        )


class PublicInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    parent_trace_id: str
    scenario_id: str
    domain: DomainName
    requested_model: str
    response_model: str
    prompt_version: str
    run_count: int = Field(ge=1)
    mode: ReplayMode
    cache_policy: str
    original_selected_action: str | None = None
    original_memory_snapshot: list[AgentInputMemory]
    replay_results: list[ReplayResult] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_investigation(cls, investigation: Investigation) -> "PublicInvestigation":
        return cls(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            domain=investigation.domain,
            requested_model=investigation.requested_model,
            response_model=investigation.response_model,
            prompt_version=investigation.prompt_version,
            run_count=investigation.run_count,
            mode=investigation.mode,
            cache_policy=investigation.cache_policy,
            original_selected_action=investigation.original_selected_action,
            original_memory_snapshot=investigation.original_memory_snapshot,
            replay_results=investigation.replay_results,
            created_at=investigation.created_at,
        )


class RunScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    runner: Literal["fake", "openai"] = "fake"


class CreateInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    mode: ReplayMode = ReplayMode.FAST
    run_count: int | None = Field(default=None, ge=1)


class IndividualReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["remove", "disable", "all"] = "all"
    memory_id: str | None = None


class PairwiseReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_a: str | None = None
    memory_b: str | None = None
    all_pairs: bool = True
    shared_baseline_runs: bool = True
    fresh_baseline_per_pair: bool = False


class CacheClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all", "scenario", "request_hash"]
    scenario_id: str | None = None
    request_hash: str | None = None


class CacheClearResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all", "scenario", "request_hash"]
    cleared: int | bool


class InvestigationResultsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation: PublicInvestigation
    suspicion_ranking: SuspicionRankingArtifact | None = None
    contradictions: ContradictionAnalysisArtifact | None = None
    pairwise_replay: PairwiseReplayArtifact | None = None
    memory_controls: MemoryControlsArtifact | None = None


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
