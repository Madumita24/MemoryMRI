from __future__ import annotations

import argparse
import json
from pathlib import Path

from memory_mri.analysis.engine import InvestigationAnalysisEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze investigation suspicion and contradictions"
    )
    parser.add_argument(
        "--database-url",
        default="sqlite:///../artifacts/memory_mri.db",
        help="SQLAlchemy database URL",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="../artifacts",
        help="Path to artifacts directory",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name, help_text in [
        ("rank-memories", "Run deterministic and semantic memory ranking"),
        ("analyze-contradictions", "Run deterministic and semantic contradiction analysis"),
        ("compare-suspicion-replay", "Compare ranking hypotheses with replay evidence"),
        ("show-evidence", "Show ranking and contradiction evidence together"),
        ("export-analysis", "Export artifact paths for an investigation"),
    ]:
        command = subparsers.add_parser(command_name, help=help_text)
        command.add_argument("--investigation-id", required=True)

    args = parser.parse_args()
    engine = InvestigationAnalysisEngine(
        database_url=args.database_url,
        artifacts_dir=Path(args.artifacts_dir).resolve(),
    )

    if args.command == "rank-memories":
        result = engine.rank_memories(args.investigation_id).model_dump(mode="json")
    elif args.command == "analyze-contradictions":
        result = engine.analyze_contradictions(args.investigation_id).model_dump(mode="json")
    elif args.command == "compare-suspicion-replay":
        result = engine.compare_suspicion_replay(args.investigation_id).model_dump(mode="json")
    elif args.command == "show-evidence":
        result = engine.show_evidence(args.investigation_id)
    elif args.command == "export-analysis":
        result = engine.export_analysis(args.investigation_id)
    else:
        raise SystemExit(f"unsupported command: {args.command}")

    if args.format == "json":
        print(json.dumps(result, indent=2))
        return
    if args.command == "export-analysis":
        for key, value in result.items():
            print(f"{key}: {value}")
        return
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
