from pathlib import Path

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.engine.benchmark import BenchmarkService


def test_benchmark_aggregation(tmp_path) -> None:
    data_dir = Path(__file__).resolve().parents[2] / "benchmark" / "data"
    artifact_path = tmp_path / "baseline-summary.json"
    service = BenchmarkService(
        database_url=f"sqlite:///{tmp_path / 'bench.db'}",
        runner=FakeAgentRunner(),
        data_dir=data_dir,
    )
    summary = service.run_baseline(artifact_path)
    assert summary["total_scenarios"] == 30
    assert artifact_path.exists()
    assert "customer_support" in summary["results_by_domain"]
