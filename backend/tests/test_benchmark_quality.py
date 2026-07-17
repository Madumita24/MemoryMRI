from pathlib import Path

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.engine.benchmark import BenchmarkService


def test_mixed_baseline_quality(tmp_path) -> None:
    data_dir = Path(__file__).resolve().parents[2] / "benchmark" / "data"
    artifact_path = tmp_path / "day1-mixed-baseline-summary.json"
    service = BenchmarkService(
        database_url=f"sqlite:///{tmp_path / 'mixed.db'}",
        runner=FakeAgentRunner(),
        data_dir=data_dir,
    )
    summary = service.run_baseline(artifact_path)

    total = int(summary["total_scenarios"])
    passed = int(summary["passed_scenarios"])
    assert total == 30
    assert 0 < passed < total

    domain_results = summary["results_by_domain"]
    for domain_name in ("customer_support", "devops", "workplace_expense"):
        result = domain_results[domain_name]
        assert result["passed"] > 0
        assert result["failed"] > 0

    scenario_results = summary["scenario_results"]
    assert any(result["passed"] for result in scenario_results)
    failed_categories = [
        category
        for category, result in summary["results_by_failure_category"].items()
        if result["failed"] > 0
    ]
    assert len(failed_categories) >= 2
