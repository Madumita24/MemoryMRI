from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIRunnerFailure
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository


def test_trace_persistence(tmp_path, benchmark_cases) -> None:
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    case = benchmark_cases[0]
    repository.import_case(case)
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    repository.save_trace(trace)
    session.commit()

    counts = repository.list_tables()
    assert counts["memories"] >= 3
    assert counts["scenarios"] == 1
    assert counts["traces"] == 1
    stored = repository.get_trace(trace.trace_id)
    assert stored is not None
    assert stored.agent_input.scenario_id == case.scenario.id
    assert stored.evaluation.evaluator_result is not None
    assert stored.evaluation.evaluator_result.expected_action == case.scenario.expected_action


def test_trace_retrieval_helpers(tmp_path, benchmark_cases) -> None:
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    case = benchmark_cases[0]
    repository.import_case(case)
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    repository.save_trace(trace)
    session.commit()

    assert repository.get_trace(trace.trace_id) is not None
    assert len(repository.list_traces_for_scenario(case.scenario.id)) == 1


def test_error_trace_persistence_and_failed_listing(tmp_path, benchmark_cases) -> None:
    session = create_sqlite_session(f"sqlite:///{tmp_path / 'memory.db'}")
    repository = BenchmarkRepository(session)
    case = benchmark_cases[0]
    repository.import_case(case)
    trace = FakeAgentRunner().run_scenario(case.scenario, case.memories)
    trace.selected_action = None
    trace.structured_response = None
    trace.action_arguments = {}
    trace.cited_memory_ids = []
    trace.concise_rationale = None
    trace.uncertainty = None
    trace.needs_human_review = None
    trace.evaluation.evaluator_result = None
    trace.passed = False
    trace.error = OpenAIRunnerFailure(
        code="transient_openai_error",
        message="network issue",
        retryable=True,
        attempts=2,
    ).to_trace_error()
    repository.save_trace(trace)
    session.commit()

    failed = repository.list_failed_traces()
    assert len(failed) == 1
    assert failed[0].error is not None
    assert failed[0].evaluation.evaluator_result is None
