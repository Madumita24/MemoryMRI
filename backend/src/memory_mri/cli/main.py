from __future__ import annotations

import argparse
from pathlib import Path

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.engine.benchmark import BenchmarkService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Memory MRI Day 1 baseline benchmark")
    parser.add_argument(
        "--database-url",
        default="sqlite:///../artifacts/memory_mri.db",
        help="SQLAlchemy database URL",
    )
    parser.add_argument(
        "--data-dir",
        default="../benchmark/data",
        help="Path to benchmark data directory",
    )
    parser.add_argument(
        "--artifact-path",
        default="../artifacts/baseline-summary.json",
        help="Path to write the summary artifact",
    )
    args = parser.parse_args()

    service = BenchmarkService(
        database_url=args.database_url,
        runner=FakeAgentRunner(),
        data_dir=Path(args.data_dir).resolve(),
    )
    service.run_baseline(Path(args.artifact_path).resolve())


if __name__ == "__main__":
    main()
