from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path

from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.benchmark import BenchmarkService
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.engine.gpt_baseline import GPTBaselineService
from memory_mri.engine.repair_proposals import RepairProposalEngine
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import ReplayMode


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory MRI Day 2 CLI")
    parser.add_argument("--database-url", default="sqlite:///../artifacts/memory_mri.db")
    parser.add_argument("--data-dir", default="../benchmark/data")
    parser.add_argument("--artifacts-dir", default="../artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_scenario = subparsers.add_parser("run-scenario")
    run_scenario.add_argument("--scenario-id", required=True)
    run_scenario.add_argument("--runner", choices=["fake", "openai"], default="fake")

    run_benchmark = subparsers.add_parser("run-benchmark")
    run_benchmark.add_argument("--runner", choices=["fake", "openai"], default="fake")
    run_benchmark.add_argument(
        "--artifact-path",
        default="../artifacts/day2-benchmark-summary.json",
    )
    run_benchmark.add_argument(
        "--summary-json-path",
        default="../artifacts/gpt-baseline-summary.json",
    )
    run_benchmark.add_argument("--summary-md-path", default="../artifacts/gpt-baseline-summary.md")
    run_benchmark.add_argument("--traces-dir", default="../artifacts/gpt-baseline-traces")
    run_benchmark.add_argument("--cache-enabled", choices=["true", "false"], default=None)

    inspect_trace = subparsers.add_parser("inspect-trace")
    inspect_trace.add_argument("--trace-id", required=True)

    create_inv = subparsers.add_parser("create-investigation")
    create_inv.add_argument("--trace-id", required=True)
    create_inv.add_argument("--mode", choices=["fast", "deep"], default="fast")
    create_inv.add_argument("--run-count", type=int, default=None)

    individual = subparsers.add_parser("individual-replay")
    individual.add_argument("--investigation-id", required=True)
    individual.add_argument("--operation", choices=["all", "remove", "disable"], default="all")
    individual.add_argument("--memory-id", default=None)

    rank = subparsers.add_parser("rank-suspicion")
    rank.add_argument("--investigation-id", required=True)

    contradictions = subparsers.add_parser("detect-contradictions")
    contradictions.add_argument("--investigation-id", required=True)

    pairwise = subparsers.add_parser("pairwise-replay")
    pairwise.add_argument("--investigation-id", required=True)
    pairwise.add_argument("--memory-a", default=None)
    pairwise.add_argument("--memory-b", default=None)
    pairwise.add_argument("--all-pairs", action="store_true")

    clear_cache = subparsers.add_parser("clear-cache")
    clear_cache.add_argument("--mode", choices=["all", "scenario", "request-hash"], required=True)
    clear_cache.add_argument("--scenario-id", default=None)
    clear_cache.add_argument("--request-hash", default=None)

    generate_proposal = subparsers.add_parser("generate-proposal")
    generate_proposal.add_argument("--investigation-id", required=True)

    list_proposals = subparsers.add_parser("list-proposals")
    list_proposals.add_argument("--investigation-id", required=True)

    show_proposal = subparsers.add_parser("show-proposal")
    show_proposal.add_argument("--proposal-id", required=True)

    explain_no_repair = subparsers.add_parser("explain-no-repair")
    explain_no_repair.add_argument("--proposal-id", required=True)

    export_proposal = subparsers.add_parser("export-proposal")
    export_proposal.add_argument("--proposal-id", required=True)

    approve_proposal = subparsers.add_parser("approve-proposal")
    approve_proposal.add_argument("--proposal-id", required=True)
    approve_proposal.add_argument("--approval-reason", required=True)
    approve_proposal.add_argument("--notes", default=None)

    reject_proposal = subparsers.add_parser("reject-proposal")
    reject_proposal.add_argument("--proposal-id", required=True)
    reject_proposal.add_argument("--rejection-reason", required=True)
    reject_proposal.add_argument("--notes", default=None)

    apply_proposal = subparsers.add_parser("apply-proposal")
    apply_proposal.add_argument("--proposal-id", required=True)

    revert_proposal = subparsers.add_parser("revert-proposal")
    revert_proposal.add_argument("--proposal-id", required=True)
    revert_proposal.add_argument("--revert-reason", required=True)

    list_versions = subparsers.add_parser("list-memory-versions")
    list_versions.add_argument("--scenario-id", required=True)

    show_version = subparsers.add_parser("show-memory-version")
    show_version.add_argument("--version-id", required=True)

    compare_versions = subparsers.add_parser("compare-memory-versions")
    compare_versions.add_argument("--from", dest="from_version", required=True)
    compare_versions.add_argument("--to", dest="to_version", required=True)

    preview_diff = subparsers.add_parser("preview-memory-diff")
    preview_diff.add_argument("--proposal-id", required=True)

    show_diff = subparsers.add_parser("show-memory-diff")
    show_diff.add_argument("--diff-id", required=True)

    export_diff = subparsers.add_parser("export-memory-diff")
    export_diff.add_argument("--diff-id", required=True)
    export_diff.add_argument("--format", choices=["json", "markdown"], required=True)

    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve()

    if args.command == "run-scenario":
        _run_scenario(args.database_url, data_dir, args.scenario_id, args.runner)
        return
    if args.command == "run-benchmark":
        _run_benchmark(args, data_dir)
        return
    if args.command == "inspect-trace":
        trace = BenchmarkRepository(create_sqlite_session(args.database_url)).get_trace(
            args.trace_id
        )
        if trace is None:
            raise SystemExit(f"Unknown trace ID: {args.trace_id}")
        print(trace.model_dump_json(indent=2))
        return

    replay_engine = CounterfactualReplayEngine(
        database_url=args.database_url,
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
    )
    analysis_engine = InvestigationAnalysisEngine(
        database_url=args.database_url,
        artifacts_dir=artifacts_dir,
    )
    proposal_engine = RepairProposalEngine(
        database_url=args.database_url,
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
    )

    if args.command == "create-investigation":
        investigation = replay_engine.create_investigation(
            parent_trace_id=args.trace_id,
            mode=ReplayMode(args.mode),
            run_count=args.run_count,
        )
        print(investigation.model_dump_json(indent=2))
        return
    if args.command == "individual-replay":
        if args.operation == "all":
            result = replay_engine.run_individual_ablation(args.investigation_id)
        elif args.operation == "remove":
            if args.memory_id is None:
                raise SystemExit("--memory-id is required for remove")
            replay_engine.replay_without_memory(args.investigation_id, args.memory_id)
            result = replay_engine.load_investigation(args.investigation_id)
        else:
            if args.memory_id is None:
                raise SystemExit("--memory-id is required for disable")
            replay_engine.replay_with_memory_disabled(args.investigation_id, args.memory_id)
            result = replay_engine.load_investigation(args.investigation_id)
        print(result.model_dump_json(indent=2))
        return
    if args.command == "rank-suspicion":
        print(analysis_engine.rank_memories(args.investigation_id).model_dump_json(indent=2))
        return
    if args.command == "detect-contradictions":
        print(
            analysis_engine.analyze_contradictions(args.investigation_id).model_dump_json(indent=2)
        )
        return
    if args.command == "pairwise-replay":
        print(
            replay_engine.replay_pairwise(
                args.investigation_id,
                memory_a=args.memory_a,
                memory_b=args.memory_b,
                all_pairs=args.all_pairs,
            ).model_dump_json(indent=2)
        )
        return
    if args.command == "clear-cache":
        runner = OpenAIAgentRunner(OpenAISettings.from_env())
        if args.mode == "all":
            print(runner.clear_cache())
        elif args.mode == "scenario":
            if args.scenario_id is None:
                raise SystemExit("--scenario-id is required for scenario mode")
            print(runner.clear_cache_for_scenario(args.scenario_id))
        else:
            if args.request_hash is None:
                raise SystemExit("--request-hash is required for request-hash mode")
            print(runner.clear_cache_for_request_hash(args.request_hash))
        return
    if args.command == "generate-proposal":
        print(proposal_engine.generate_proposal(args.investigation_id).model_dump_json(indent=2))
        return
    if args.command == "list-proposals":
        proposals = proposal_engine.list_proposals(args.investigation_id)
        print(json.dumps([proposal.model_dump(mode="json") for proposal in proposals], indent=2))
        return
    if args.command == "show-proposal":
        print(proposal_engine.get_proposal(args.proposal_id).model_dump_json(indent=2))
        return
    if args.command == "explain-no-repair":
        print(proposal_engine.explain_no_repair(args.proposal_id))
        return
    if args.command == "export-proposal":
        print(json.dumps(proposal_engine.export_proposal(args.proposal_id), indent=2))
        return
    if args.command == "approve-proposal":
        print(
            proposal_engine.approve_proposal(
                args.proposal_id,
                approval_reason=args.approval_reason,
                notes=args.notes,
            ).model_dump_json(indent=2)
        )
        return
    if args.command == "reject-proposal":
        print(
            proposal_engine.reject_proposal(
                args.proposal_id,
                rejection_reason=args.rejection_reason,
                notes=args.notes,
            ).model_dump_json(indent=2)
        )
        return
    if args.command == "apply-proposal":
        print(proposal_engine.apply_proposal(args.proposal_id).model_dump_json(indent=2))
        return
    if args.command == "revert-proposal":
        print(
            proposal_engine.revert_proposal(
                args.proposal_id,
                revert_reason=args.revert_reason,
            ).model_dump_json(indent=2)
        )
        return
    if args.command == "list-memory-versions":
        versions = proposal_engine.list_memory_versions(args.scenario_id)
        print(json.dumps([version.model_dump(mode="json") for version in versions], indent=2))
        return
    if args.command == "show-memory-version":
        print(proposal_engine.show_memory_version(args.version_id).model_dump_json(indent=2))
        return
    if args.command == "compare-memory-versions":
        print(
            proposal_engine.compare_memory_versions(
                args.from_version,
                args.to_version,
            ).model_dump_json(indent=2)
        )
        return
    if args.command == "preview-memory-diff":
        print(proposal_engine.preview_memory_diff(args.proposal_id).model_dump_json(indent=2))
        return
    if args.command == "show-memory-diff":
        print(proposal_engine.get_memory_diff(args.diff_id).model_dump_json(indent=2))
        return
    if args.command == "export-memory-diff":
        print(proposal_engine.export_memory_diff(args.diff_id, args.format))
        return
    raise SystemExit(f"Unsupported command: {args.command}")


def _run_scenario(database_url: str, data_dir: Path, scenario_id: str, runner_name: str) -> None:
    cases = {case.scenario.id: case for case in load_benchmark_cases(data_dir)}
    case = cases.get(scenario_id)
    if case is None:
        raise SystemExit(f"Unknown scenario ID: {scenario_id}")
    runner = (
        FakeAgentRunner() if runner_name == "fake" else OpenAIAgentRunner(OpenAISettings.from_env())
    )
    try:
        trace = runner.run_scenario(case.scenario, case.memories)
    except OpenAIRunnerError as exc:
        if exc.trace is None:
            raise
        trace = exc.trace
    repository = BenchmarkRepository(create_sqlite_session(database_url))
    repository.import_case(case)
    repository.save_trace(trace)
    repository.session.commit()
    print(trace.model_dump_json(indent=2))


def _run_benchmark(args: argparse.Namespace, data_dir: Path) -> None:
    if args.runner == "fake":
        benchmark_service = BenchmarkService(
            database_url=args.database_url,
            runner=FakeAgentRunner(),
            data_dir=data_dir,
        )
        summary = benchmark_service.run_baseline(Path(args.artifact_path).resolve())
        print(json.dumps(summary, indent=2))
        return
    settings = OpenAISettings.from_env()
    if args.cache_enabled is not None:
        settings = replace(settings, cache_enabled=args.cache_enabled == "true")
    gpt_service = GPTBaselineService(
        database_url=args.database_url,
        runner=OpenAIAgentRunner(settings),
        data_dir=data_dir,
        git_commit_hash=_git_commit_hash(),
        git_branch_state=_git_branch_state(),
    )
    summary = gpt_service.run_official_baseline(
        summary_json_path=Path(args.summary_json_path).resolve(),
        summary_md_path=Path(args.summary_md_path).resolve(),
        traces_dir=Path(args.traces_dir).resolve(),
    )
    print(json.dumps(summary, indent=2))


def _git_commit_hash() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _git_branch_state() -> str:
    return subprocess.check_output(["git", "status", "--short", "--branch"], text=True).strip()


if __name__ == "__main__":
    main()
