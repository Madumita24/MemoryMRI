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
    AgentInput,
    AgentScenario,
    ExecutionTrace,
    Memory,
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


class OpenAIRunnerError(Exception):
    def __init__(self, failure: OpenAIRunnerFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


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

    def run_scenario(self, scenario: AgentScenario, memories: list[Memory]) -> ExecutionTrace:
        payload = self.build_request_payload(scenario, memories)
        prompt = load_domain_prompt(
            scenario.domain, self.settings.prompt_version, scenario.allowed_actions
        )
        cached = self._load_cache(payload, prompt)
        scenario_memories = [memory for memory in memories if memory.id in scenario.memory_ids]
        if cached is not None:
            decision = OpenAIActionSelection.model_validate(cached["decision"])
            self._validate_decision(decision, payload)
            evaluator_result = evaluate_action(scenario, decision.selected_action)
            return ExecutionTrace(
                trace_id=new_trace_id(),
                scenario_id=scenario.id,
                run_id=new_run_id(),
                model=self.settings.model,
                prompt_version=self.settings.prompt_version,
                retrieved_memory_ids=[memory.id for memory in scenario_memories],
                memory_snapshot=scenario_memories,
                selected_action=decision.selected_action,
                action_arguments=self._normalize_action_arguments(decision),
                tool_call={
                    "cache_hit": True,
                    "cited_memory_ids": decision.cited_memory_ids,
                    "needs_human_review": decision.needs_human_review,
                },
                evaluator_result=evaluator_result,
                passed=evaluator_result.passed,
                latency_ms=0,
                token_usage=cached.get("usage", {}),
                created_at=time_to_datetime(time.time()),
            )

        if not self.settings.api_key:
            raise OpenAIRunnerError(
                OpenAIRunnerFailure(
                    code="missing_api_key",
                    message="OPENAI_API_KEY is required for OpenAIAgentRunner",
                    retryable=False,
                    attempts=0,
                )
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
                self._write_cache(payload, prompt, decision, usage)
                evaluator_result = evaluate_action(scenario, decision.selected_action)
                return ExecutionTrace(
                    trace_id=new_trace_id(),
                    scenario_id=scenario.id,
                    run_id=new_run_id(),
                    model=getattr(response, "model", self.settings.model),
                    prompt_version=self.settings.prompt_version,
                    retrieved_memory_ids=[memory.id for memory in scenario_memories],
                    memory_snapshot=scenario_memories,
                    selected_action=decision.selected_action,
                    action_arguments=self._normalize_action_arguments(decision),
                    tool_call={
                        "response_id": getattr(response, "id", None),
                        "cited_memory_ids": decision.cited_memory_ids,
                        "needs_human_review": decision.needs_human_review,
                    },
                    evaluator_result=evaluator_result,
                    passed=evaluator_result.passed,
                    latency_ms=latency_ms,
                    token_usage=usage,
                    created_at=time_to_datetime(time.time()),
                )
            except OpenAIRunnerError:
                raise
            except ValidationError as exc:
                raise OpenAIRunnerError(
                    OpenAIRunnerFailure(
                        code="invalid_model_output",
                        message=f"Model output failed validation: {exc}",
                        retryable=False,
                        attempts=attempts,
                    )
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
                    raise OpenAIRunnerError(last_failure) from exc
            except (AuthenticationError, BadRequestError) as exc:
                raise OpenAIRunnerError(
                    OpenAIRunnerFailure(
                        code="permanent_openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
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
                raise OpenAIRunnerError(failure) from exc
            except OpenAIError as exc:
                raise OpenAIRunnerError(
                    OpenAIRunnerFailure(
                        code="openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc

        if last_failure is None:
            last_failure = OpenAIRunnerFailure(
                code="unknown_openai_failure",
                message="OpenAI runner failed without a captured exception",
                retryable=False,
                attempts=attempts,
            )
        raise OpenAIRunnerError(last_failure)

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

    def _cache_key(self, payload: AgentInput, prompt: str) -> str:
        hashed = hashlib.sha256()
        hashed.update(self.settings.model.encode("utf-8"))
        hashed.update(self.settings.prompt_version.encode("utf-8"))
        hashed.update(prompt.encode("utf-8"))
        hashed.update(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8"))
        return hashed.hexdigest()

    def _cache_path(self, payload: AgentInput, prompt: str) -> Path:
        return self.settings.cache_dir / f"{self._cache_key(payload, prompt)}.json"

    def _load_cache(self, payload: AgentInput, prompt: str) -> dict[str, Any] | None:
        if not self.settings.cache_enabled:
            return None
        path = self._cache_path(payload, prompt)
        if not path.exists():
            return None
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def _write_cache(
        self,
        payload: AgentInput,
        prompt: str,
        decision: OpenAIActionSelection,
        usage: dict[str, int],
    ) -> None:
        if not self.settings.cache_enabled:
            return
        path = self._cache_path(payload, prompt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"decision": decision.model_dump(mode="json"), "usage": usage}, indent=2),
            encoding="utf-8",
        )


def time_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
