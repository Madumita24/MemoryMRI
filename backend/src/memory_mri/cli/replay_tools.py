from __future__ import annotations

import argparse
from pathlib import Path

from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.schemas import ReplayMode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run individual-memory replay investigations")
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
        "--artifacts-dir",
        default="../artifacts",
        help="Path to artifacts directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create-investigation",
        help="Create a replay investigation",
    )
    create_parser.add_argument("--trace-id", required=True)
    create_parser.add_argument("--mode", choices=["fast", "deep"], default="fast")
    create_parser.add_argument("--run-count", type=int, default=None)

    list_parser = subparsers.add_parser("list-memories", help="List memories in an investigation")
    list_parser.add_argument("--investigation-id", required=True)

    remove_parser = subparsers.add_parser("replay-remove", help="Replay with one memory removed")
    remove_parser.add_argument("--investigation-id", required=True)
    remove_parser.add_argument("--memory-id", required=True)

    disable_parser = subparsers.add_parser("replay-disable", help="Replay with one memory disabled")
    disable_parser.add_argument("--investigation-id", required=True)
    disable_parser.add_argument("--memory-id", required=True)

    results_parser = subparsers.add_parser("replay-results", help="Retrieve replay results")
    results_parser.add_argument("--investigation-id", required=True)

    pairwise_parser = subparsers.add_parser("pairwise-replay", help="Run pairwise replay")
    pairwise_parser.add_argument("--investigation-id", required=True)
    pairwise_parser.add_argument("--memory-a", default=None)
    pairwise_parser.add_argument("--memory-b", default=None)
    pairwise_parser.add_argument("--all-pairs", action="store_true")

    no_memory_parser = subparsers.add_parser(
        "no-memory-control",
        help="Run the no-memory control for an investigation",
    )
    no_memory_parser.add_argument("--investigation-id", required=True)

    isolate_parser = subparsers.add_parser(
        "isolate-memory",
        help="Run the single-memory isolation control",
    )
    isolate_parser.add_argument("--investigation-id", required=True)
    isolate_parser.add_argument("--memory-id", required=True)

    compare_parser = subparsers.add_parser(
        "compare-individual-pairwise",
        help="Compare individual and pairwise replay evidence",
    )
    compare_parser.add_argument("--investigation-id", required=True)

    classify_parser = subparsers.add_parser(
        "classify-memory-dependence",
        help="Classify the investigation's memory dependence",
    )
    classify_parser.add_argument("--investigation-id", required=True)

    export_pairwise_parser = subparsers.add_parser(
        "export-pairwise",
        help="Export pairwise replay and memory-control artifacts",
    )
    export_pairwise_parser.add_argument("--investigation-id", required=True)

    args = parser.parse_args()
    engine = CounterfactualReplayEngine(
        database_url=args.database_url,
        data_dir=Path(args.data_dir).resolve(),
        artifacts_dir=Path(args.artifacts_dir).resolve(),
    )

    if args.command == "create-investigation":
        investigation = engine.create_investigation(
            parent_trace_id=args.trace_id,
            mode=ReplayMode(args.mode),
            run_count=args.run_count,
        )
        print(investigation.investigation_id)
        return
    if args.command == "list-memories":
        for memory in engine.list_memories(args.investigation_id):
            print(f"{memory.memory_id}: {memory.content}")
        return
    if args.command == "replay-remove":
        replay_result = engine.replay_without_memory(args.investigation_id, args.memory_id)
        print(replay_result.model_dump_json(indent=2))
        return
    if args.command == "replay-disable":
        replay_result = engine.replay_with_memory_disabled(args.investigation_id, args.memory_id)
        print(replay_result.model_dump_json(indent=2))
        return
    if args.command == "replay-results":
        results = engine.get_replay_results(args.investigation_id)
        print("[\n" + ",\n".join(result.model_dump_json(indent=2) for result in results) + "\n]")
        return
    if args.command == "pairwise-replay":
        artifact = engine.replay_pairwise(
            args.investigation_id,
            memory_a=args.memory_a,
            memory_b=args.memory_b,
            all_pairs=args.all_pairs,
        )
        print(artifact.model_dump_json(indent=2))
        return
    if args.command == "no-memory-control":
        control_result = engine.run_no_memory_control(args.investigation_id)
        print(control_result.model_dump_json(indent=2))
        return
    if args.command == "isolate-memory":
        control_result = engine.run_isolate_memory(args.investigation_id, args.memory_id)
        print(control_result.model_dump_json(indent=2))
        return
    if args.command == "compare-individual-pairwise":
        artifact = engine.replay_pairwise(args.investigation_id, all_pairs=True)
        print(artifact.model_dump_json(indent=2))
        return
    if args.command == "classify-memory-dependence":
        classification = engine.classify_memory_dependence(args.investigation_id)
        print(classification.value)
        return
    if args.command == "export-pairwise":
        pairwise = engine.replay_pairwise(args.investigation_id, all_pairs=True)
        controls = engine.export_memory_controls(args.investigation_id)
        pairwise_path = (
            engine._investigation_dir(pairwise.investigation_id) / "pairwise-replay.json"
        )
        controls_path = (
            engine._investigation_dir(controls.investigation_id) / "memory-controls.json"
        )
        print(f'{{\n  "pairwise": "{pairwise_path}",\n  "controls": "{controls_path}"\n}}')
        return
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
