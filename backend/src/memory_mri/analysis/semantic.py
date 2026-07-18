from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memory_mri.analysis.models import (
    ContradictionAnalysisInput,
    SemanticMemoryAnalysis,
    SemanticMemoryAnalysisResponse,
    SemanticPairAnalysis,
    SemanticPairAnalysisResponse,
    SuspicionAnalysisInput,
)
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings
from memory_mri.prompts.loader import load_analysis_prompt


class ParsedResponseLike(Protocol):
    id: str
    model: str
    usage: Any
    output_text: str


class ResponsesAPI(Protocol):
    def create(self, **kwargs: Any) -> ParsedResponseLike: ...


class OpenAIClientLike(Protocol):
    responses: ResponsesAPI


class SemanticAnalysisFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    attempts: int


class SemanticCacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_hash: str
    analysis_kind: str
    requested_model: str
    response_model: str
    prompt_version: str
    prompt_content_hash: str
    payload: dict[str, Any]
    structured_output: dict[str, Any]
    created_at: datetime
    usage: dict[str, int] = Field(default_factory=dict)
    original_model_latency_ms: int = Field(ge=0)


class SemanticAnalysisError(Exception):
    def __init__(self, failure: SemanticAnalysisFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


@dataclass(frozen=True)
class SemanticAnalysisResult:
    analyses: list[SemanticMemoryAnalysis] | list[SemanticPairAnalysis]
    usage: dict[str, int]
    response_model: str
    prompt_hash: str
    request_hash: str
    cache_hit: bool


class InvestigationSemanticAnalyzer:
    def __init__(
        self,
        *,
        settings: OpenAISettings | None = None,
        prompt_settings: SemanticAnalysisSettings | None = None,
        client: OpenAIClientLike | None = None,
    ) -> None:
        self.settings = settings or OpenAISettings.from_env()
        self.prompt_settings = prompt_settings or SemanticAnalysisSettings.from_env()
        self._client: OpenAIClientLike | None = client
        self._last_response: ParsedResponseLike | None = None

    def analyze_memory_suspicion(
        self,
        payload: SuspicionAnalysisInput,
    ) -> SemanticAnalysisResult:
        prompt = load_analysis_prompt(
            "memory_suspicion",
            self.prompt_settings.suspicion_prompt_version,
        )
        prompt_hash = _hash_text(prompt)
        request_hash = self._cache_key(
            "memory_suspicion",
            payload.model_dump(mode="json"),
            prompt_hash,
        )
        cached = self._load_cached_memory_response(request_hash)
        if cached is not None:
            analyses = self._validate_memory_response(cached, payload)
            return SemanticAnalysisResult(
                analyses=analyses.analyses,
                usage={},
                response_model=self.settings.model,
                prompt_hash=prompt_hash,
                request_hash=request_hash,
                cache_hit=True,
            )

        response, usage = self._execute(
            response_model=SemanticMemoryAnalysisResponse,
            prompt=prompt,
            payload=payload.model_dump(mode="json"),
        )
        analyses = self._validate_memory_response(response, payload)
        self._write_cache(
            request_hash=request_hash,
            analysis_kind="memory_suspicion",
            prompt_version=self.prompt_settings.suspicion_prompt_version,
            prompt_hash=prompt_hash,
            payload=payload.model_dump(mode="json"),
            response=response.model_dump(mode="json"),
            usage=usage,
            response_model=getattr(self._last_response, "model", self.settings.model),
        )
        return SemanticAnalysisResult(
            analyses=analyses.analyses,
            usage=usage,
            response_model=getattr(self._last_response, "model", self.settings.model),
            prompt_hash=prompt_hash,
            request_hash=request_hash,
            cache_hit=False,
        )

    def analyze_pair_relationships(
        self,
        payload: ContradictionAnalysisInput,
    ) -> SemanticAnalysisResult:
        prompt = load_analysis_prompt(
            "memory_contradiction",
            self.prompt_settings.contradiction_prompt_version,
        )
        prompt_hash = _hash_text(prompt)
        request_hash = self._cache_key(
            "memory_contradiction",
            payload.model_dump(mode="json"),
            prompt_hash,
        )
        cached = self._load_cached_pair_response(request_hash)
        if cached is not None:
            analyses = self._validate_pair_response(cached, payload)
            return SemanticAnalysisResult(
                analyses=analyses.pairs,
                usage={},
                response_model=self.settings.model,
                prompt_hash=prompt_hash,
                request_hash=request_hash,
                cache_hit=True,
            )

        response, usage = self._execute(
            response_model=SemanticPairAnalysisResponse,
            prompt=prompt,
            payload=payload.model_dump(mode="json"),
        )
        analyses = self._validate_pair_response(response, payload)
        self._write_cache(
            request_hash=request_hash,
            analysis_kind="memory_contradiction",
            prompt_version=self.prompt_settings.contradiction_prompt_version,
            prompt_hash=prompt_hash,
            payload=payload.model_dump(mode="json"),
            response=response.model_dump(mode="json"),
            usage=usage,
            response_model=getattr(self._last_response, "model", self.settings.model),
        )
        return SemanticAnalysisResult(
            analyses=analyses.pairs,
            usage=usage,
            response_model=getattr(self._last_response, "model", self.settings.model),
            prompt_hash=prompt_hash,
            request_hash=request_hash,
            cache_hit=False,
        )

    def _execute(
        self,
        *,
        response_model: type[ResponseModelT],
        prompt: str,
        payload: dict[str, Any],
    ) -> tuple[ResponseModelT, dict[str, int]]:
        if not self.settings.api_key:
            raise SemanticAnalysisError(
                SemanticAnalysisFailure(
                    code="missing_api_key",
                    message="OPENAI_API_KEY is required for semantic analysis",
                    retryable=False,
                    attempts=0,
                )
            )

        attempts = 0
        while attempts <= self.settings.max_retries:
            attempts += 1
            try:
                started = time.perf_counter()
                response = self._get_client().responses.create(
                    model=self.settings.model,
                    instructions=prompt,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": json.dumps(payload, indent=2),
                                }
                            ],
                        }
                    ],
                    reasoning=self._build_reasoning(),
                    text=self._build_text_config(response_model),
                    timeout=self.settings.timeout_seconds,
                )
                self._last_response = response
                _ = int((time.perf_counter() - started) * 1000)
                parsed = response_model.model_validate_json(getattr(response, "output_text", ""))
                return parsed, self._extract_usage(response)
            except ValidationError as exc:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="invalid_model_output",
                        message=f"Semantic analysis output failed validation: {exc}",
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
                if attempts > self.settings.max_retries:
                    raise SemanticAnalysisError(
                        SemanticAnalysisFailure(
                            code="transient_openai_error",
                            message=str(exc),
                            retryable=True,
                            attempts=attempts,
                        )
                    ) from exc
            except (AuthenticationError, BadRequestError) as exc:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="permanent_openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc
            except APIStatusError as exc:
                retryable = exc.status_code >= 500
                if retryable and attempts <= self.settings.max_retries:
                    continue
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="openai_status_error",
                        message=str(exc),
                        retryable=retryable,
                        attempts=attempts,
                    )
                ) from exc
            except OpenAIError as exc:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc

        raise SemanticAnalysisError(
            SemanticAnalysisFailure(
                code="unknown_semantic_failure",
                message="Semantic analysis failed without a captured exception",
                retryable=False,
                attempts=attempts,
            )
        )

    def _validate_memory_response(
        self,
        response: SemanticMemoryAnalysisResponse,
        payload: SuspicionAnalysisInput,
    ) -> SemanticMemoryAnalysisResponse:
        known_ids = {memory.memory_id for memory in payload.memories}
        seen_ids: set[str] = set()
        for analysis in response.analyses:
            if analysis.memory_id not in known_ids:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="invalid_memory_id",
                        message=f"Unknown memory ID in semantic analysis: {analysis.memory_id}",
                        retryable=False,
                        attempts=1,
                    )
                )
            if analysis.memory_id in seen_ids:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="duplicate_memory_id",
                        message=f"Duplicate semantic analysis entry for {analysis.memory_id}",
                        retryable=False,
                        attempts=1,
                    )
                )
            seen_ids.add(analysis.memory_id)
            unknown_related = [
                memory_id for memory_id in analysis.related_memory_ids if memory_id not in known_ids
            ]
            if unknown_related:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="invalid_related_memory_ids",
                        message=f"Unknown related memory IDs: {unknown_related}",
                        retryable=False,
                        attempts=1,
                    )
                )
        if seen_ids != known_ids:
            raise SemanticAnalysisError(
                SemanticAnalysisFailure(
                    code="incomplete_memory_analysis",
                    message="Semantic analysis did not cover every memory in the snapshot",
                    retryable=False,
                    attempts=1,
                )
            )
        return response

    def _validate_pair_response(
        self,
        response: SemanticPairAnalysisResponse,
        payload: ContradictionAnalysisInput,
    ) -> SemanticPairAnalysisResponse:
        known_ids = {memory.memory_id for memory in payload.memories}
        expected_pairs = {
            tuple(sorted((pair.memory_a_id, pair.memory_b_id))) for pair in payload.pairs
        }
        seen_pairs: set[tuple[str, str]] = set()
        for analysis in response.pairs:
            if analysis.memory_a_id not in known_ids or analysis.memory_b_id not in known_ids:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="invalid_memory_id",
                        message="Semantic contradiction analysis returned an unknown memory ID",
                        retryable=False,
                        attempts=1,
                    )
                )
            ordered_pair = sorted((analysis.memory_a_id, analysis.memory_b_id))
            canonical: tuple[str, str] = (ordered_pair[0], ordered_pair[1])
            if canonical in seen_pairs:
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="duplicate_pair",
                        message=f"Duplicate contradiction pair result: {canonical}",
                        retryable=False,
                        attempts=1,
                    )
                )
            if canonical != (analysis.memory_a_id, analysis.memory_b_id):
                raise SemanticAnalysisError(
                    SemanticAnalysisFailure(
                        code="noncanonical_pair_order",
                        message="Semantic contradiction pairs must use canonical ordering",
                        retryable=False,
                        attempts=1,
                    )
                )
            seen_pairs.add(canonical)
        if seen_pairs != expected_pairs:
            raise SemanticAnalysisError(
                SemanticAnalysisFailure(
                    code="incomplete_pair_analysis",
                    message="Semantic contradiction analysis did not cover every unique pair",
                    retryable=False,
                    attempts=1,
                )
            )
        return response

    def _build_text_config(self, response_model: type[BaseModel]) -> dict[str, object]:
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

    def _build_reasoning(self) -> dict[str, str] | None:
        if self.settings.reasoning_effort is None:
            return None
        return {"effort": self.settings.reasoning_effort}

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

    def _cache_key(self, analysis_kind: str, payload: dict[str, Any], prompt_hash: str) -> str:
        request = {
            "analysis_kind": analysis_kind,
            "payload": payload,
            "requested_model": self.settings.model,
            "prompt_hash": prompt_hash,
            "reasoning_effort": self.settings.reasoning_effort,
            "verbosity": self.settings.verbosity,
        }
        hashed = hashlib.sha256()
        hashed.update(json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return hashed.hexdigest()

    def _cache_path(self, request_hash: str) -> Path:
        return self.settings.cache_dir / "semantic_analysis" / f"{request_hash}.json"

    def _load_cached_memory_response(
        self,
        request_hash: str,
    ) -> SemanticMemoryAnalysisResponse | None:
        return cast(
            SemanticMemoryAnalysisResponse | None,
            self._load_cached_response(request_hash, SemanticMemoryAnalysisResponse),
        )

    def _load_cached_pair_response(
        self,
        request_hash: str,
    ) -> SemanticPairAnalysisResponse | None:
        return cast(
            SemanticPairAnalysisResponse | None,
            self._load_cached_response(request_hash, SemanticPairAnalysisResponse),
        )

    def _load_cached_response(
        self,
        request_hash: str,
        response_model: type[ResponseModelT],
    ) -> ResponseModelT | None:
        if not self.settings.cache_enabled:
            return None
        path = self._cache_path(request_hash)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = SemanticCacheRecord.model_validate(payload)
        try:
            return response_model.model_validate(record.structured_output)
        except ValidationError as exc:
            raise SemanticAnalysisError(
                SemanticAnalysisFailure(
                    code="invalid_cached_output",
                    message=f"Cached semantic analysis failed validation: {exc}",
                    retryable=False,
                    attempts=1,
                )
            ) from exc

    def _write_cache(
        self,
        *,
        request_hash: str,
        analysis_kind: str,
        prompt_version: str,
        prompt_hash: str,
        payload: dict[str, Any],
        response: dict[str, Any],
        usage: dict[str, int],
        response_model: str,
    ) -> None:
        if not self.settings.cache_enabled:
            return
        path = self._cache_path(request_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            SemanticCacheRecord(
                request_hash=request_hash,
                analysis_kind=analysis_kind,
                requested_model=self.settings.model,
                response_model=response_model,
                prompt_version=prompt_version,
                prompt_content_hash=prompt_hash,
                payload=payload,
                structured_output=response,
                created_at=datetime.now(timezone.utc),
                usage=usage,
                original_model_latency_ms=0,
            ).model_dump_json(indent=2),
            encoding="utf-8",
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


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


ResponseModelT = TypeVar(
    "ResponseModelT",
    SemanticMemoryAnalysisResponse,
    SemanticPairAnalysisResponse,
)
