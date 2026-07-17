from memory_mri.agents.fake import FakeAgentRunner


def test_fake_runner_executes(benchmark_cases) -> None:
    case = benchmark_cases[0]
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    assert trace.scenario_id == case.scenario.id
    assert trace.selected_action in case.scenario.allowed_actions
    assert len(trace.retrieved_memory_ids) == len(case.scenario.memory_ids)


def test_fake_runner_produces_mixed_outcomes(benchmark_cases) -> None:
    runner = FakeAgentRunner()
    passed = 0
    failed = 0
    for case in benchmark_cases:
        trace = runner.run_scenario(case.scenario, case.memories)
        if trace.passed:
            passed += 1
        else:
            failed += 1
    assert passed > 0
    assert failed > 0
