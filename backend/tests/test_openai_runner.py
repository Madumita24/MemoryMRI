from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, BadRequestError

from memory_mri.agents import openai_runner as openai_runner_module
from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import (
    OpenAIActionSelection,
    OpenAIAgentRunner,
    OpenAICacheRecord,
    OpenAIRunnerError,
)
from memory_mri.config import OpenAISettings


@dataclass
class FakeUsage:
    input_tokens: int = 11
    output_tokens: int = 7
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
    id: str = "resp_test"
    model: str = "gpt-5.6"


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


def make_settings(
    tmp_path: Path,
    api_key: str | None = "test-key",
    max_retries: int = 2,
    cache_enabled: bool = False,
    model: str = "gpt-5.6",
    prompt_version: str = "v1",
) -> OpenAISettings:
    return OpenAISettings(
        api_key=api_key,
        model=model,
        timeout_seconds=5.0,
        max_retries=max_retries,
        cache_enabled=cache_enabled,
        prompt_version=prompt_version,
        reasoning_effort=None,
        verbosity="low",
        cache_dir=tmp_path / "openai-cache",
    )


def make_decision(
    case, action: str | None = None, memory_ids: list[str] | None = None
) -> OpenAIActionSelection:
    return OpenAIActionSelection(
        selected_action=action or case.scenario.expected_action,
        action_arguments=[],
        cited_memory_ids=memory_ids or [case.memories[0].id],
        concise_rationale="Current policy and evidence support this action.",
        uncertainty=0.2,
        needs_human_review=False,
    )


def make_response(decision: OpenAIActionSelection) -> FakeParsedResponse:
    return FakeParsedResponse(output_text=decision.model_dump_json())


def test_openai_runner_valid_structured_response(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    response = make_response(make_decision(case))
    response.usage = FakeUsage()
    client = FakeClient([response])
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    trace = runner.run_scenario(case.scenario, case.memories)

    assert trace.selected_action == case.scenario.expected_action
    assert trace.tool_call["response_id"] == "resp_test"
    assert trace.token_usage["total_tokens"] == 18
    assert trace.cache.hit is False
    assert trace.evaluation.evaluator_result is not None
    assert trace.requested_model == "gpt-5.6"
    assert trace.response_model == "gpt-5.6"
    assert trace.execution_source == "live"
    assert trace.request_token_usage is not None
    assert trace.cached_original_token_usage is None
    assert trace.billable_api_call is True


def test_openai_runner_rejects_unknown_selected_action(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([make_response(make_decision(case, action="NOT_VALID"))])
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "invalid_selected_action"


def test_openai_runner_rejects_unknown_cited_memory_id(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([make_response(make_decision(case, memory_ids=["memory_missing"]))])
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "invalid_cited_memory_ids"


def test_openai_runner_rejects_malformed_response(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([FakeParsedResponse(output_text="")])
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "invalid_model_output"
    assert exc_info.value.trace is not None
    assert exc_info.value.trace.error is not None


def test_openai_runner_handles_timeout(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([APITimeoutError(request=None)])  # type: ignore[arg-type]
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, max_retries=0),
        client=client,
    )

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "transient_openai_error"
    assert exc_info.value.failure.retryable is True


def test_openai_runner_retries_transient_error(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient(
        [
            APIConnectionError(message="temporary connection issue", request=None),  # type: ignore[arg-type]
            make_response(make_decision(case)),
        ]
    )
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    trace = runner.run_scenario(case.scenario, case.memories)

    assert trace.selected_action == case.scenario.expected_action
    assert len(client.responses.calls) == 2


def test_openai_runner_handles_permanent_api_error(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code=400, request=request)
    client = FakeClient([BadRequestError(message="bad request", response=response, body=None)])
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path), client=client)

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "permanent_openai_error"
    assert exc_info.value.failure.retryable is False


def test_openai_runner_requires_api_key(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, api_key=None),
        client=FakeClient([]),
    )

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "missing_api_key"
    assert exc_info.value.trace is not None


def test_fake_runner_still_operational(benchmark_cases) -> None:
    case = benchmark_cases[0]
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    assert trace.selected_action in case.scenario.allowed_actions


def test_identical_requests_produce_same_cache_key(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path))

    left = runner.build_request_hash(case.scenario, case.memories)
    right = runner.build_request_hash(case.scenario, case.memories)

    assert left == right


def test_memory_change_produces_new_cache_key(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0].model_copy(deep=True)
    changed_case = benchmark_cases[0].model_copy(deep=True)
    changed_case.memories[0].content = f"{changed_case.memories[0].content} Updated."
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path))

    assert runner.build_request_hash(case.scenario, case.memories) != runner.build_request_hash(
        changed_case.scenario, changed_case.memories
    )


def test_prompt_version_change_produces_new_cache_key(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner_v1 = OpenAIAgentRunner(settings=make_settings(tmp_path, prompt_version="v1"))
    runner_v2 = OpenAIAgentRunner(settings=make_settings(tmp_path, prompt_version="v2"))

    prompt_v1 = "prompt version one"
    prompt_v2 = "prompt version two"
    assert runner_v1._cache_key(
        runner_v1.build_request_payload(case.scenario, case.memories),
        prompt_v1,
    ) != runner_v2._cache_key(
        runner_v2.build_request_payload(case.scenario, case.memories),
        prompt_v2,
    )


def test_prompt_content_change_produces_new_cache_key(
    benchmark_cases, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = benchmark_cases[0]
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path, prompt_version="v1"))

    monkeypatch.setattr(
        openai_runner_module,
        "load_domain_prompt",
        lambda domain, version, allowed_actions: "prompt A",
    )
    hash_a = runner.build_request_hash(case.scenario, case.memories)

    monkeypatch.setattr(
        openai_runner_module,
        "load_domain_prompt",
        lambda domain, version, allowed_actions: "prompt B",
    )
    hash_b = runner.build_request_hash(case.scenario, case.memories)

    assert hash_a != hash_b


def test_model_change_produces_new_cache_key(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner_a = OpenAIAgentRunner(settings=make_settings(tmp_path, model="gpt-5.6"))
    runner_b = OpenAIAgentRunner(settings=make_settings(tmp_path, model="gpt-5.6-mini"))

    assert runner_a.build_request_hash(case.scenario, case.memories) != runner_b.build_request_hash(
        case.scenario, case.memories
    )


def test_expected_action_change_does_not_affect_request_key(
    benchmark_cases, tmp_path: Path
) -> None:
    original_case = benchmark_cases[0].model_copy(deep=True)
    modified_case = benchmark_cases[0].model_copy(deep=True)
    modified_case.scenario.expected_action = modified_case.scenario.allowed_actions[-1]
    runner = OpenAIAgentRunner(settings=make_settings(tmp_path))

    assert runner.build_request_hash(
        original_case.scenario, original_case.memories
    ) == runner.build_request_hash(modified_case.scenario, modified_case.memories)


def test_invalid_responses_are_not_cached(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([FakeParsedResponse(output_text="")])
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, cache_enabled=True),
        client=client,
    )

    with pytest.raises(OpenAIRunnerError):
        runner.run_scenario(case.scenario, case.memories)

    assert list((tmp_path / "openai-cache").glob("*.json")) == []


def test_cached_responses_are_revalidated(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, cache_enabled=True),
        client=FakeClient([make_response(make_decision(case))]),
    )
    first_trace = runner.run_scenario(case.scenario, case.memories)
    assert first_trace.cache.hit is False

    cache_files = list((tmp_path / "openai-cache").glob("*.json"))
    assert len(cache_files) == 1
    cache_payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    cache_payload["structured_response"]["cited_memory_ids"][0] = "missing_memory_id"
    cache_files[0].write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")

    cached_runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, cache_enabled=True),
        client=FakeClient([]),
    )
    with pytest.raises(OpenAIRunnerError) as exc_info:
        cached_runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "invalid_cited_memory_ids"


def test_cache_hit_skips_second_api_request(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    client = FakeClient([make_response(make_decision(case))])
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, cache_enabled=True),
        client=client,
    )

    first_trace = runner.run_scenario(case.scenario, case.memories)
    second_trace = runner.run_scenario(case.scenario, case.memories)

    assert first_trace.cache.hit is False
    assert second_trace.cache.hit is True
    assert second_trace.execution_source == "cache"
    assert second_trace.request_token_usage is None
    assert second_trace.cached_original_token_usage is not None
    assert second_trace.billable_api_call is False
    assert len(client.responses.calls) == 1


def test_invalid_cached_unknown_action_is_rejected(benchmark_cases, tmp_path: Path) -> None:
    case = benchmark_cases[0]
    runner = OpenAIAgentRunner(
        settings=make_settings(tmp_path, cache_enabled=True),
        client=FakeClient([]),
    )
    request_hash = runner.build_request_hash(case.scenario, case.memories)
    cache_dir = tmp_path / "openai-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_record = OpenAICacheRecord(
        request_hash=request_hash,
        scenario_id=case.scenario.id,
        agent_input=runner.build_request_payload(case.scenario, case.memories),
        structured_response={
            "selected_action": "NOT_VALID",
            "action_arguments": {},
            "cited_memory_ids": [case.memories[0].id],
            "concise_rationale": "bad cache",
            "uncertainty": 0.1,
            "needs_human_review": False,
        },
        requested_model="gpt-5.6",
        response_model="gpt-5.6-sol",
        model="gpt-5.6-sol",
        prompt_version="v1",
        prompt_content_hash=runner._prompt_content_hash(runner._load_prompt(case.scenario)),
        agent_input_schema_version="day2a-v1",
        inference_settings={"verbosity": "low"},
        created_at=datetime.now(timezone.utc),
        usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        original_model_latency_ms=10,
    )
    (cache_dir / f"{request_hash}.json").write_text(
        cache_record.model_dump_json(indent=2),
        encoding="utf-8",
    )

    with pytest.raises(OpenAIRunnerError) as exc_info:
        runner.run_scenario(case.scenario, case.memories)

    assert exc_info.value.failure.code == "invalid_selected_action"
