from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from memory_mri.agents.base import AgentRunner
from memory_mri.config import OpenAISettings
from memory_mri.evaluation import evaluate_action
from memory_mri.prompts.loader import load_domain_prompt
from memory_mri.schemas import (
    AGENT_INPUT_SCHEMA_VERSION,
    AgentInput,
    AgentScenario,
    ExecutionTrace,
    Memory,
    StructuredAgentResponse,
    TraceCacheStatus,
    TraceErrorDetails,
    TraceEvaluation,
    build_agent_input,
    new_run_id,
    new_trace_id,
)


class ParsedResponseLike(Protocol):
    id: str
    model: str
    usage: Any
    output_text: str


class ResponsesAPI(Protocol):
    def create(self, **kwargs: Any) -> ParsedResponseLike: ...


class OpenAIClientLike(Protocol):
    responses: ResponsesAPI


class OpenAIActionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_action: str
    action_arguments: list["OpenAIActionArgument"]
    cited_memory_ids: list[str]
    concise_rationale: str = Field(min_length=1, max_length=280)
    uncertainty: float = Field(ge=0.0, le=1.0)
    needs_human_review: bool

    @field_validator("cited_memory_ids")
    @classmethod
    def unique_citations(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("cited_memory_ids must be unique")
        return value


class OpenAIActionArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str


class OpenAIRunnerFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    attempts: int

    def to_trace_error(self) -> TraceErrorDetails:
        return TraceErrorDetails(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            attempts=self.attempts,
        )


class OpenAICacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_hash: str
    scenario_id: str
    agent_input: AgentInput
    structured_response: StructuredAgentResponse
    requested_model: str
    response_model: str
    model: str
    prompt_version: str
    prompt_content_hash: str
    agent_input_schema_version: str = AGENT_INPUT_SCHEMA_VERSION
    inference_settings: dict[str, str]
    created_at: datetime
    usage: dict[str, int] = Field(default_factory=dict)
    original_model_latency_ms: int = Field(ge=0)


class OpenAIRunnerError(Exception):
    def __init__(self, failure: OpenAIRunnerFailure, trace: ExecutionTrace | None = None) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.trace = trace


class OpenAIAgentRunner(AgentRunner):
    model_name = "configured-openai"
    prompt_version = "unconfigured"

    def __init__(
        self,
        settings: OpenAISettings | None = None,
        client: OpenAIClientLike | None = None,
    ) -> None:
        self.settings = settings or OpenAISettings.from_env()
        self.model_name = self.settings.model
        self.prompt_version = self.settings.prompt_version
        self._client: OpenAIClientLike | None = client

    def build_request_payload(self, scenario: AgentScenario, memories: list[Memory]) -> AgentInput:
        return build_agent_input(scenario, memories)

    def build_request_hash(self, scenario: AgentScenario, memories: list[Memory]) -> str:
        payload = self.build_request_payload(scenario, memories)
        prompt = self._load_prompt(scenario)
        return self._cache_key(payload, prompt)

    def run_scenario(self, scenario: AgentScenario, memories: list[Memory]) -> ExecutionTrace:
        payload = self.build_request_payload(scenario, memories)
        prompt = self._load_prompt(scenario)
        prompt_content_hash = self._prompt_content_hash(prompt)
        request_hash = self._cache_key(payload, prompt)
        memory_snapshot = list(payload.memories)
        retrieved_memory_ids = [memory.memory_id for memory in memory_snapshot]

        cache_started = time.perf_counter()
        cached = self._load_cache(request_hash)
        cache_lookup_latency_ms = int((time.perf_counter() - cache_started) * 1000)
        if cached is not None:
            decision = self._decision_from_structured_response(cached.structured_response)
            self._validate_decision(decision, payload)
            evaluator_result = evaluate_action(scenario, decision.selected_action)
            return self._build_trace(
                scenario=scenario,
                payload=payload,
                request_hash=request_hash,
                prompt_content_hash=prompt_content_hash,
                memory_snapshot=memory_snapshot,
                retrieved_memory_ids=retrieved_memory_ids,
                requested_model=cached.requested_model,
                response_model=cached.response_model,
                structured_response=cached.structured_response,
                evaluator_result=evaluator_result,
                execution_source="cache",
                latency_ms=cache_lookup_latency_ms,
                cache_lookup_latency_ms=cache_lookup_latency_ms,
                original_model_latency_ms=cached.original_model_latency_ms,
                token_usage={},
                request_token_usage=None,
                cached_original_token_usage=cached.usage,
                billable_api_call=False,
                cache_status=TraceCacheStatus(
                    enabled=self.settings.cache_enabled,
                    request_hash=request_hash,
                    hit=True,
                    cache_path=str(self._cache_path(request_hash)),
                    cached_at=cached.created_at,
                ),
                tool_call={"cache_hit": True},
            )

        if not self.settings.api_key:
            failure = OpenAIRunnerFailure(
                code="missing_api_key",
                message="OPENAI_API_KEY is required for OpenAIAgentRunner",
                retryable=False,
                attempts=0,
            )
            raise OpenAIRunnerError(
                failure,
                trace=self._build_error_trace(
                    scenario=scenario,
                    payload=payload,
                    request_hash=request_hash,
                    prompt_content_hash=prompt_content_hash,
                    memory_snapshot=memory_snapshot,
                    retrieved_memory_ids=retrieved_memory_ids,
                    failure=failure,
                ),
            )

        attempts = 0
        last_failure: OpenAIRunnerFailure | None = None
        while attempts <= self.settings.max_retries:
            attempts += 1
            started = time.perf_counter()
            try:
                response = self._get_client().responses.create(
                    model=self.settings.model,
                    instructions=prompt,
                    input=self._build_responses_input(payload),
                    reasoning=self._build_reasoning(),
                    text=self._build_text_config(OpenAIActionSelection),
                    timeout=self.settings.timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                decision = self._extract_decision(response)
                self._validate_decision(decision, payload)
                usage = self._extract_usage(response)
                evaluator_result = evaluate_action(scenario, decision.selected_action)
                structured_response = self._structured_response_from_decision(decision)
                response_model = getattr(response, "model", self.settings.model)
                self._write_cache(
                    OpenAICacheRecord(
                        request_hash=request_hash,
                        scenario_id=scenario.id,
                        agent_input=payload,
                        structured_response=structured_response,
                        requested_model=self.settings.model,
                        response_model=response_model,
                        model=response_model,
                        prompt_version=self.settings.prompt_version,
                        prompt_content_hash=prompt_content_hash,
                        agent_input_schema_version=payload.schema_version,
                        inference_settings=self._inference_settings(),
                        created_at=time_to_datetime(time.time()),
                        usage=usage,
                        original_model_latency_ms=latency_ms,
                    )
                )
                return self._build_trace(
                    scenario=scenario,
                    payload=payload,
                    request_hash=request_hash,
                    prompt_content_hash=prompt_content_hash,
                    memory_snapshot=memory_snapshot,
                    retrieved_memory_ids=retrieved_memory_ids,
                    requested_model=self.settings.model,
                    response_model=response_model,
                    structured_response=structured_response,
                    evaluator_result=evaluator_result,
                    execution_source="live",
                    latency_ms=latency_ms,
                    cache_lookup_latency_ms=cache_lookup_latency_ms,
                    original_model_latency_ms=None,
                    token_usage=usage,
                    request_token_usage=usage,
                    cached_original_token_usage=None,
                    billable_api_call=True,
                    cache_status=TraceCacheStatus(
                        enabled=self.settings.cache_enabled,
                        request_hash=request_hash,
                        hit=False,
                        cache_path=str(self._cache_path(request_hash)),
                    ),
                    tool_call={
                        "response_id": getattr(response, "id", None),
                        "cache_hit": False,
                    },
                )
            except OpenAIRunnerError as exc:
                if exc.trace is not None:
                    raise
                raise OpenAIRunnerError(
                    exc.failure,
                    trace=self._build_error_trace(
                        scenario=scenario,
                        payload=payload,
                        request_hash=request_hash,
                        prompt_content_hash=prompt_content_hash,
                        memory_snapshot=memory_snapshot,
                        retrieved_memory_ids=retrieved_memory_ids,
                        failure=exc.failure,
                    ),
                ) from exc
            except ValidationError as exc:
                failure = OpenAIRunnerFailure(
                    code="invalid_model_output",
                    message=f"Model output failed validation: {exc}",
                    retryable=False,
                    attempts=attempts,
                )
                raise OpenAIRunnerError(
                    failure,
                    trace=self._build_error_trace(
                        scenario=scenario,
                        payload=payload,
                        request_hash=request_hash,
                        prompt_content_hash=prompt_content_hash,
                        memory_snapshot=memory_snapshot,
                        retrieved_memory_ids=retrieved_memory_ids,
                        failure=failure,
                    ),
                ) from exc
            except (
                APITimeoutError,
                APIConnectionError,
                RateLimitError,
                InternalServerError,
                ConflictError,
            ) as exc:
                last_failure = OpenAIRunnerFailure(
                    code="transient_openai_error",
                    message=str(exc),
                    retryable=True,
                    attempts=attempts,
                )
                if attempts > self.settings.max_retries:
                    raise OpenAIRunnerError(
                        last_failure,
                        trace=self._build_error_trace(
                            scenario=scenario,
                            payload=payload,
                            request_hash=request_hash,
                            prompt_content_hash=prompt_content_hash,
                            memory_snapshot=memory_snapshot,
                            retrieved_memory_ids=retrieved_memory_ids,
                            failure=last_failure,
                        ),
                    ) from exc
            except (AuthenticationError, BadRequestError) as exc:
                failure = OpenAIRunnerFailure(
                    code="permanent_openai_error",
                    message=str(exc),
                    retryable=False,
                    attempts=attempts,
                )
                raise OpenAIRunnerError(
                    failure,
                    trace=self._build_error_trace(
                        scenario=scenario,
                        payload=payload,
                        request_hash=request_hash,
                        prompt_content_hash=prompt_content_hash,
                        memory_snapshot=memory_snapshot,
                        retrieved_memory_ids=retrieved_memory_ids,
                        failure=failure,
                    ),
                ) from exc
            except APIStatusError as exc:
                retryable = exc.status_code >= 500
                failure = OpenAIRunnerFailure(
                    code="openai_status_error",
                    message=str(exc),
                    retryable=retryable,
                    attempts=attempts,
                )
                if retryable and attempts <= self.settings.max_retries:
                    last_failure = failure
                    continue
                raise OpenAIRunnerError(
                    failure,
                    trace=self._build_error_trace(
                        scenario=scenario,
                        payload=payload,
                        request_hash=request_hash,
                        prompt_content_hash=prompt_content_hash,
                        memory_snapshot=memory_snapshot,
                        retrieved_memory_ids=retrieved_memory_ids,
                        failure=failure,
                    ),
                ) from exc
            except OpenAIError as exc:
                failure = OpenAIRunnerFailure(
                    code="openai_error",
                    message=str(exc),
                    retryable=False,
                    attempts=attempts,
                )
                raise OpenAIRunnerError(
                    failure,
                    trace=self._build_error_trace(
                        scenario=scenario,
                        payload=payload,
                        request_hash=request_hash,
                        prompt_content_hash=prompt_content_hash,
                        memory_snapshot=memory_snapshot,
                        retrieved_memory_ids=retrieved_memory_ids,
                        failure=failure,
                    ),
                ) from exc

        if last_failure is None:
            last_failure = OpenAIRunnerFailure(
                code="unknown_openai_failure",
                message="OpenAI runner failed without a captured exception",
                retryable=False,
                attempts=attempts,
            )
        raise OpenAIRunnerError(
            last_failure,
            trace=self._build_error_trace(
                scenario=scenario,
                payload=payload,
                request_hash=request_hash,
                prompt_content_hash=prompt_content_hash,
                memory_snapshot=memory_snapshot,
                retrieved_memory_ids=retrieved_memory_ids,
                failure=last_failure,
            ),
        )

    def _get_client(self) -> OpenAIClientLike:
        if self._client is None:
            self._client = cast(
                OpenAIClientLike,
                OpenAI(
                    api_key=self.settings.api_key,
                    timeout=self.settings.timeout_seconds,
                    max_retries=0,
                ),
            )
        return self._client

    def _load_prompt(self, scenario: AgentScenario) -> str:
        return load_domain_prompt(
            scenario.domain, self.settings.prompt_version, scenario.allowed_actions
        )

    def _build_reasoning(self) -> dict[str, str] | None:
        if self.settings.reasoning_effort is None:
            return None
        return {"effort": self.settings.reasoning_effort}

    def _build_text_config(self, response_model: type[OpenAIActionSelection]) -> dict[str, object]:
        config: dict[str, object] = {
            "format": {
                "type": "json_schema",
                "name": response_model.__name__,
                "strict": True,
                "schema": to_strict_json_schema(response_model),
            }
        }
        if self.settings.verbosity is not None:
            config["verbosity"] = self.settings.verbosity
        return config

    def _build_responses_input(self, payload: AgentInput) -> list[dict[str, object]]:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": payload.model_dump_json(indent=2),
                    }
                ],
            }
        ]

    def _extract_decision(self, response: ParsedResponseLike) -> OpenAIActionSelection:
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise OpenAIRunnerError(
                OpenAIRunnerFailure(
                    code="invalid_model_output",
                    message="Missing structured output text",
                    retryable=False,
                    attempts=1,
                )
            )
        return OpenAIActionSelection.model_validate_json(output_text)

    def _validate_decision(self, decision: OpenAIActionSelection, payload: AgentInput) -> None:
        if decision.selected_action not in payload.allowed_actions:
            raise OpenAIRunnerError(
                OpenAIRunnerFailure(
                    code="invalid_selected_action",
                    message=f"Unknown selected action: {decision.selected_action}",
                    retryable=False,
                    attempts=1,
                )
            )
        known_memory_ids = {memory.memory_id for memory in payload.memories}
        unknown_memory_ids = [
            memory_id
            for memory_id in decision.cited_memory_ids
            if memory_id not in known_memory_ids
        ]
        if unknown_memory_ids:
            raise OpenAIRunnerError(
                OpenAIRunnerFailure(
                    code="invalid_cited_memory_ids",
                    message=f"Unknown cited memory IDs: {unknown_memory_ids}",
                    retryable=False,
                    attempts=1,
                )
            )

    def _extract_usage(self, response: ParsedResponseLike) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        dumped = usage.model_dump(mode="json")
        result: dict[str, int] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = dumped.get(key)
            if isinstance(value, int):
                result[key] = value
        return result

    def _normalize_action_arguments(self, decision: OpenAIActionSelection) -> dict[str, str]:
        return {argument.name: argument.value for argument in decision.action_arguments}

    def _structured_response_from_decision(
        self, decision: OpenAIActionSelection
    ) -> StructuredAgentResponse:
        return StructuredAgentResponse(
            selected_action=decision.selected_action,
            action_arguments=self._normalize_action_arguments(decision),
            cited_memory_ids=decision.cited_memory_ids,
            concise_rationale=decision.concise_rationale,
            uncertainty=decision.uncertainty,
            needs_human_review=decision.needs_human_review,
        )

    def _decision_from_structured_response(
        self, response: StructuredAgentResponse
    ) -> OpenAIActionSelection:
        return OpenAIActionSelection(
            selected_action=response.selected_action,
            action_arguments=[
                OpenAIActionArgument(name=name, value=str(value))
                for name, value in response.action_arguments.items()
            ],
            cited_memory_ids=response.cited_memory_ids,
            concise_rationale=response.concise_rationale,
            uncertainty=response.uncertainty,
            needs_human_review=response.needs_human_review,
        )

    def _inference_settings(self) -> dict[str, str]:
        settings: dict[str, str] = {}
        if self.settings.reasoning_effort is not None:
            settings["reasoning_effort"] = self.settings.reasoning_effort
        if self.settings.verbosity is not None:
            settings["verbosity"] = self.settings.verbosity
        return settings

    def _prompt_content_hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _cache_key(self, payload: AgentInput, prompt: str) -> str:
        request = {
            "scenario_id": payload.scenario_id,
            "domain": payload.domain.value,
            "user_input": payload.user_input,
            "allowed_actions": payload.allowed_actions,
            "memories": [memory.model_dump(mode="json") for memory in payload.memories],
            "requested_model": self.settings.model,
            "prompt_version": self.settings.prompt_version,
            "prompt_content_hash": self._prompt_content_hash(prompt),
            "agent_input_schema_version": payload.schema_version,
            "inference_settings": self._inference_settings(),
        }
        hashed = hashlib.sha256()
        hashed.update(json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return hashed.hexdigest()

    def _cache_path(self, request_hash: str) -> Path:
        return self.settings.cache_dir / f"{request_hash}.json"

    def _load_cache(self, request_hash: str) -> OpenAICacheRecord | None:
        if not self.settings.cache_enabled:
            return None
        path = self._cache_path(request_hash)
        if not path.exists():
            return None
        return self._read_cache_record(path)

    def _write_cache(self, record: OpenAICacheRecord) -> None:
        if not self.settings.cache_enabled:
            return
        path = self._cache_path(record.request_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def cache_status(self, scenario: AgentScenario, memories: list[Memory]) -> TraceCacheStatus:
        request_hash = self.build_request_hash(scenario, memories)
        path = self._cache_path(request_hash)
        if not path.exists():
            return TraceCacheStatus(
                enabled=self.settings.cache_enabled,
                request_hash=request_hash,
                hit=False,
                cache_path=str(path),
            )
        record = self._read_cache_record(path)
        if record is None:
            return TraceCacheStatus(
                enabled=self.settings.cache_enabled,
                request_hash=request_hash,
                hit=False,
                cache_path=str(path),
            )
        return TraceCacheStatus(
            enabled=self.settings.cache_enabled,
            request_hash=request_hash,
            hit=True,
            cache_path=str(path),
            cached_at=record.created_at,
        )

    def clear_cache_for_request_hash(self, request_hash: str) -> bool:
        path = self._cache_path(request_hash)
        if not path.exists():
            return False
        path.unlink()
        return True

    def clear_cache_for_scenario(self, scenario_id: str) -> int:
        removed = 0
        if not self.settings.cache_dir.exists():
            return 0
        for path in self.settings.cache_dir.glob("*.json"):
            payload = self._read_cache_payload(path)
            if payload.get("scenario_id") == scenario_id:
                path.unlink()
                removed += 1
        return removed

    def clear_cache(self) -> int:
        removed = 0
        if not self.settings.cache_dir.exists():
            return 0
        for path in self.settings.cache_dir.glob("*.json"):
            path.unlink()
            removed += 1
        return removed

    def _read_cache_payload(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}

    def _read_cache_record(self, path: Path) -> OpenAICacheRecord | None:
        payload = self._read_cache_payload(path)
        if not payload:
            return None
        try:
            return OpenAICacheRecord.model_validate(payload)
        except ValidationError:
            return None

    def _build_trace(
        self,
        *,
        scenario: AgentScenario,
        payload: AgentInput,
        request_hash: str,
        prompt_content_hash: str,
        memory_snapshot: list[Any],
        retrieved_memory_ids: list[str],
        requested_model: str,
        response_model: str,
        structured_response: StructuredAgentResponse,
        evaluator_result: Any,
        execution_source: str,
        latency_ms: int,
        cache_lookup_latency_ms: int | None,
        original_model_latency_ms: int | None,
        token_usage: dict[str, int],
        request_token_usage: dict[str, int] | None,
        cached_original_token_usage: dict[str, int] | None,
        billable_api_call: bool,
        cache_status: TraceCacheStatus,
        tool_call: dict[str, Any] | None,
    ) -> ExecutionTrace:
        return ExecutionTrace(
            trace_id=new_trace_id(),
            scenario_id=scenario.id,
            run_id=new_run_id(),
            domain=scenario.domain,
            user_input=scenario.user_input,
            agent_input=payload,
            requested_model=requested_model,
            response_model=response_model,
            model=response_model,
            prompt_version=self.settings.prompt_version,
            prompt_content_hash=prompt_content_hash,
            agent_input_schema_version=payload.schema_version,
            request_hash=request_hash,
            retrieved_memory_ids=retrieved_memory_ids,
            memory_snapshot=memory_snapshot,
            structured_response=structured_response,
            selected_action=structured_response.selected_action,
            action_arguments=structured_response.action_arguments,
            cited_memory_ids=structured_response.cited_memory_ids,
            concise_rationale=structured_response.concise_rationale,
            uncertainty=structured_response.uncertainty,
            needs_human_review=structured_response.needs_human_review,
            tool_call=tool_call,
            evaluation=TraceEvaluation(evaluator_result=evaluator_result),
            passed=evaluator_result.passed,
            execution_source=execution_source,
            cache_lookup_latency_ms=cache_lookup_latency_ms,
            original_model_latency_ms=original_model_latency_ms,
            latency_ms=latency_ms,
            token_usage=token_usage,
            request_token_usage=request_token_usage,
            cached_original_token_usage=cached_original_token_usage,
            billable_api_call=billable_api_call,
            cache=cache_status,
            created_at=time_to_datetime(time.time()),
        )

    def _build_error_trace(
        self,
        *,
        scenario: AgentScenario,
        payload: AgentInput,
        request_hash: str,
        prompt_content_hash: str,
        memory_snapshot: list[Any],
        retrieved_memory_ids: list[str],
        failure: OpenAIRunnerFailure,
    ) -> ExecutionTrace:
        return ExecutionTrace(
            trace_id=new_trace_id(),
            scenario_id=scenario.id,
            run_id=new_run_id(),
            domain=scenario.domain,
            user_input=scenario.user_input,
            agent_input=payload,
            requested_model=self.settings.model,
            response_model=self.settings.model,
            model=self.settings.model,
            prompt_version=self.settings.prompt_version,
            prompt_content_hash=prompt_content_hash,
            agent_input_schema_version=payload.schema_version,
            request_hash=request_hash,
            retrieved_memory_ids=retrieved_memory_ids,
            memory_snapshot=memory_snapshot,
            execution_source="error",
            cache_lookup_latency_ms=0,
            original_model_latency_ms=None,
            latency_ms=0,
            token_usage={},
            request_token_usage=None,
            cached_original_token_usage=None,
            billable_api_call=False,
            cache=TraceCacheStatus(
                enabled=self.settings.cache_enabled,
                request_hash=request_hash,
                hit=False,
                cache_path=str(self._cache_path(request_hash)),
            ),
            error=failure.to_trace_error(),
            created_at=time_to_datetime(time.time()),
        )


def time_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
