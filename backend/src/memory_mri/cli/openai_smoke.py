from __future__ import annotations

import argparse
from pathlib import Path

from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
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
    session = create_sqlite_session(args.database_url)
    repository = BenchmarkRepository(session)
    repository.import_case(case)
    try:
        trace = runner.run_scenario(case.scenario, case.memories)
    except OpenAIRunnerError as exc:
        if exc.trace is not None:
            repository.save_trace(exc.trace)
            session.commit()
            _write_artifact(args.artifact_path, args.scenario_id, exc.trace)
        raise
    else:
        repository.save_trace(trace)
        session.commit()

    _write_artifact(args.artifact_path, args.scenario_id, trace)
    cache_hit = trace.cache.hit if trace.cache.hit is not None else False
    print(f"{trace.scenario_id} {trace.selected_action} {trace.passed} cache_hit={cache_hit}")


def _write_artifact(artifact_path_arg: str | None, scenario_id: str, trace) -> None:  # type: ignore[no-untyped-def]
    artifact_path = (
        Path(artifact_path_arg).resolve()
        if artifact_path_arg
        else Path(f"../artifacts/openai-smoke-{scenario_id}.json").resolve()
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
