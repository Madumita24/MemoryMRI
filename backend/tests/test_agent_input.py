from memory_mri.agents.openai_runner import OpenAIAgentRunner
from memory_mri.schemas import build_agent_input


def test_agent_input_excludes_private_scenario_fields(benchmark_cases) -> None:
    case = benchmark_cases[0]
    payload = build_agent_input(case.scenario, case.memories).model_dump(mode="json")

    assert payload["scenario_id"] == case.scenario.id
    assert payload["allowed_actions"] == case.scenario.allowed_actions
    assert "expected_action" not in payload
    assert "expected_problematic_memory_ids" not in payload
    assert "failure_category" not in payload
    assert "explanation" not in payload
    assert "evaluator_config" not in payload


def test_agent_input_excludes_benchmark_only_memory_hints(benchmark_cases) -> None:
    case = benchmark_cases[0]
    payload = build_agent_input(case.scenario, case.memories).model_dump(mode="json")
    first_memory = payload["memories"][0]

    assert "benchmark_metadata" not in first_memory
    assert "fake_action_bias" not in first_memory
    assert "supports_action" not in first_memory
    assert "should_ignore" not in first_memory
    assert "interaction_group" not in first_memory
    assert "salience_boost" not in first_memory


def test_agent_input_keeps_operational_memory_fields(benchmark_cases) -> None:
    case = benchmark_cases[0]
    payload = build_agent_input(case.scenario, case.memories).model_dump(mode="json")
    first_memory = payload["memories"][0]

    assert first_memory["memory_id"] == case.memories[0].id
    assert first_memory["entity_id"] == case.memories[0].entity_id
    assert first_memory["content"] == case.memories[0].content
    assert first_memory["source"] == case.memories[0].source
    assert first_memory["status"] == case.memories[0].status.value
    assert first_memory["confidence"] == case.memories[0].confidence
    assert first_memory["retrieval_priority"] == case.memories[0].retrieval_priority
    assert first_memory["operational_metadata"] == case.memories[0].operational_metadata


def test_openai_runner_uses_serializer_not_raw_model_dump(benchmark_cases, monkeypatch) -> None:
    case = benchmark_cases[0]

    def fail_model_dump(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("raw model_dump should not be used for agent prompts")

    monkeypatch.setattr(type(case.scenario), "model_dump", fail_model_dump)
    monkeypatch.setattr(type(case.memories[0]), "model_dump", fail_model_dump)

    payload = OpenAIAgentRunner().build_request_payload(case.scenario, case.memories)
    assert payload.scenario_id == case.scenario.id
