from pathlib import Path

from memory_mri.benchmark_loader import load_benchmark_cases


def test_loads_all_scenarios() -> None:
    cases = load_benchmark_cases(Path(__file__).resolve().parents[2] / "benchmark" / "data")
    assert len(cases) == 30
    assert sum(1 for case in cases if case.scenario.domain.value == "customer_support") == 10
    assert sum(1 for case in cases if case.scenario.domain.value == "devops") == 10
    assert sum(1 for case in cases if case.scenario.domain.value == "workplace_expense") == 10
