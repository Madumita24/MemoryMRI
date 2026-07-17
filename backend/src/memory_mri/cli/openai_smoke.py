from __future__ import annotations

import argparse
from pathlib import Path

from memory_mri.agents.openai_runner import OpenAIAgentRunner
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one GPT-backed Memory MRI smoke scenario")
    parser.add_argument("--scenario-id", required=True, help="Scenario ID to run")
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
        default=None,
        help="Optional path to write the development trace artifact",
    )
    args = parser.parse_args()

    cases = load_benchmark_cases(Path(args.data_dir).resolve())
    case = next(
        (candidate for candidate in cases if candidate.scenario.id == args.scenario_id),
        None,
    )
    if case is None:
        raise SystemExit(f"Unknown scenario ID: {args.scenario_id}")

    runner = OpenAIAgentRunner(OpenAISettings.from_env())
    trace = runner.run_scenario(case.scenario, case.memories)

    session = create_sqlite_session(args.database_url)
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    repository.save_trace(trace)
    session.commit()

    artifact_path = (
        Path(args.artifact_path).resolve()
        if args.artifact_path
        else Path(f"../artifacts/openai-smoke-{args.scenario_id}.json").resolve()
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    print(f"{trace.scenario_id} {trace.selected_action} {trace.passed}")


if __name__ == "__main__":
    main()
