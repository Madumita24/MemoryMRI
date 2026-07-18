from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from memory_mri.agents.openai_runner import OpenAIAgentRunner
from memory_mri.config import OpenAISettings
from memory_mri.engine.gpt_baseline import GPTBaselineService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the official GPT Memory MRI baseline")
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
        "--summary-json-path",
        default="../artifacts/gpt-baseline-summary.json",
        help="Path to write the JSON summary artifact",
    )
    parser.add_argument(
        "--summary-md-path",
        default="../artifacts/gpt-baseline-summary.md",
        help="Path to write the Markdown summary artifact",
    )
    parser.add_argument(
        "--traces-dir",
        default="../artifacts/gpt-baseline-traces",
        help="Directory to write per-scenario traces",
    )
    parser.add_argument("--git-commit-hash", required=True, help="Git commit hash for the run")
    parser.add_argument("--git-branch-state", required=True, help="Git branch/status summary")
    parser.add_argument(
        "--cache-enabled",
        choices=["true", "false"],
        default=None,
        help="Override cache behavior for the baseline run",
    )
    args = parser.parse_args()

    settings = OpenAISettings.from_env()
    if args.cache_enabled is not None:
        settings = replace(settings, cache_enabled=args.cache_enabled == "true")

    service = GPTBaselineService(
        database_url=args.database_url,
        runner=OpenAIAgentRunner(settings),
        data_dir=Path(args.data_dir).resolve(),
        git_commit_hash=args.git_commit_hash,
        git_branch_state=args.git_branch_state,
    )
    summary = service.run_official_baseline(
        summary_json_path=Path(args.summary_json_path).resolve(),
        summary_md_path=Path(args.summary_md_path).resolve(),
        traces_dir=Path(args.traces_dir).resolve(),
    )
    overall = summary["overall"]
    status_line = (
        "attempted={attempted} evaluated={evaluated} passed={passed} failed={failed} "
        "infra_errors={infra}"
    )
    print(
        status_line.format(
            attempted=overall["attempted_scenarios"],
            evaluated=overall["evaluated_scenarios"],
            passed=overall["passed_scenarios"],
            failed=overall["failed_scenarios"],
            infra=overall["infrastructure_errors"],
        )
    )


if __name__ == "__main__":
    main()
