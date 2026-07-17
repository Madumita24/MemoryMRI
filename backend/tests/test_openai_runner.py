from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, BadRequestError

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import (
    OpenAIActionSelection,
    OpenAIAgentRunner,
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
    tmp_path: Path, api_key: str | None = "test-key", max_retries: int = 2
) -> OpenAISettings:
    return OpenAISettings(
        api_key=api_key,
        model="gpt-5.6",
        timeout_seconds=5.0,
        max_retries=max_retries,
        cache_enabled=False,
        prompt_version="v1",
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


def test_fake_runner_still_operational(benchmark_cases) -> None:
    case = benchmark_cases[0]
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    assert trace.selected_action in case.scenario.allowed_actions
