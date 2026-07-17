from memory_mri.agents.fake import FakeAgentRunner
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
