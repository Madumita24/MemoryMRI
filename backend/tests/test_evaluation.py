from memory_mri.evaluation import evaluate_action


def test_exact_action_evaluation(benchmark_cases) -> None:
    scenario = benchmark_cases[0].scenario
    result = evaluate_action(scenario, scenario.expected_action)
    assert result.passed is True
    assert result.selected_action == scenario.expected_action


def test_invalid_action_rejection(benchmark_cases) -> None:
    scenario = benchmark_cases[0].scenario.model_copy(update={"allowed_actions": ["ISSUE_REFUND"]})
    trace_case = benchmark_cases[0].model_copy(deep=True)
    trace_case.scenario = scenario
    trace_case.memories[0].benchmark_metadata["fake_action_bias"] = "NOT_REAL"

    from memory_mri.agents.fake import FakeAgentRunner

    runner = FakeAgentRunner()
    try:
        runner.run_scenario(trace_case.scenario, trace_case.memories)
    except ValueError as exc:
        assert "invalid fake action bias" in str(exc)
    else:
        raise AssertionError("expected ValueError")
