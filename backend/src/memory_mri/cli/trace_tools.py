from __future__ import annotations

import argparse
from pathlib import Path

from memory_mri.agents.openai_runner import OpenAIAgentRunner
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Memory MRI traces and GPT cache")
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    trace_parser = subparsers.add_parser("trace", help="Retrieve one trace by ID")
    trace_parser.add_argument("--trace-id", required=True)

    scenario_parser = subparsers.add_parser("scenario-traces", help="List traces for a scenario")
    scenario_parser.add_argument("--scenario-id", required=True)

    subparsers.add_parser("failed-traces", help="List failed traces")

    agent_input_parser = subparsers.add_parser(
        "agent-input", help="Inspect the exact agent-visible input for a trace"
    )
    agent_input_parser.add_argument("--trace-id", required=True)

    cache_status_parser = subparsers.add_parser("cache-status", help="Inspect cache status")
    cache_status_parser.add_argument("--scenario-id", required=True)

    clear_scenario_parser = subparsers.add_parser(
        "clear-cache-scenario", help="Clear cache entries for one scenario"
    )
    clear_scenario_parser.add_argument("--scenario-id", required=True)

    clear_hash_parser = subparsers.add_parser(
        "clear-cache-hash", help="Clear a cache entry by request hash"
    )
    clear_hash_parser.add_argument("--request-hash", required=True)

    subparsers.add_parser("clear-cache-all", help="Clear all GPT cache entries")
    args = parser.parse_args()

    cache_commands = {
        "cache-status",
        "clear-cache-scenario",
        "clear-cache-hash",
        "clear-cache-all",
    }
    if args.command in cache_commands:
        _handle_cache_command(args)
        return

    session = create_sqlite_session(args.database_url)
    repository = BenchmarkRepository(session)
    if args.command == "trace":
        trace = repository.get_trace(args.trace_id)
        if trace is None:
            raise SystemExit(f"Unknown trace ID: {args.trace_id}")
        print(trace.model_dump_json(indent=2))
        return
    if args.command == "scenario-traces":
        traces = repository.list_traces_for_scenario(args.scenario_id)
        print("[\n" + ",\n".join(trace.model_dump_json(indent=2) for trace in traces) + "\n]")
        return
    if args.command == "failed-traces":
        traces = repository.list_failed_traces()
        print("[\n" + ",\n".join(trace.model_dump_json(indent=2) for trace in traces) + "\n]")
        return
    if args.command == "agent-input":
        trace = repository.get_trace(args.trace_id)
        if trace is None:
            raise SystemExit(f"Unknown trace ID: {args.trace_id}")
        print(trace.agent_input.model_dump_json(indent=2))
        return

    raise SystemExit(f"Unsupported command: {args.command}")


def _handle_cache_command(args: argparse.Namespace) -> None:
    runner = OpenAIAgentRunner(OpenAISettings.from_env())
    if args.command == "clear-cache-all":
        print(runner.clear_cache())
        return
    if args.command == "clear-cache-hash":
        print(runner.clear_cache_for_request_hash(args.request_hash))
        return
    if not hasattr(args, "scenario_id"):
        raise SystemExit("scenario ID is required")

    cases = load_benchmark_cases(Path(args.data_dir).resolve())
    case = next(
        (candidate for candidate in cases if candidate.scenario.id == args.scenario_id),
        None,
    )
    if case is None:
        raise SystemExit(f"Unknown scenario ID: {args.scenario_id}")

    if args.command == "cache-status":
        status = runner.cache_status(case.scenario, case.memories)
        print(status.model_dump_json(indent=2))
        return
    if args.command == "clear-cache-scenario":
        print(runner.clear_cache_for_scenario(args.scenario_id))
        return

    raise SystemExit(f"Unsupported cache command: {args.command}")


if __name__ == "__main__":
    main()
