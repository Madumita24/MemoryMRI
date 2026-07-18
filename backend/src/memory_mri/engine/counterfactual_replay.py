from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from memory_mri.agents.base import AgentRunner
from memory_mri.agents.fake import FakeAgentRunner
from memory_mri.agents.openai_runner import OpenAIAgentRunner, OpenAIRunnerError
from memory_mri.benchmark_loader import load_benchmark_cases
from memory_mri.config import OpenAISettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.prompts.loader import load_domain_prompt
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    AgentInputMemory,
    AgentScenario,
    BenchmarkCase,
    ExecutionTrace,
    Intervention,
    InterventionType,
    Investigation,
    MemoryStatus,
    ReplayMode,
    ReplayResult,
    TraceErrorDetails,
)
from memory_mri.statistics import wilson_score_interval

FAST_RUNS = 3
DEEP_RUNS = 10


@dataclass(frozen=True)
class ReplayBatch:
    traces: list[ExecutionTrace]
    successful_runs: int
    total_runs: int
    success_rate: float
    action_distribution: dict[str, int]
    replay_stability: float
    errors: list[TraceErrorDetails]
    token_usage: dict[str, int]


RunnerFactory = Callable[[ExecutionTrace], AgentRunner]


class CounterfactualReplayEngine:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self.runner_factory = runner_factory or self._build_runner_for_trace
        self.case_lookup = {case.scenario.id: case for case in load_benchmark_cases(self.data_dir)}

    def create_investigation(
        self,
        *,
        parent_trace_id: str,
        mode: ReplayMode = ReplayMode.FAST,
        run_count: int | None = None,
    ) -> Investigation:
        parent_trace = self._get_trace(parent_trace_id)
        if parent_trace.passed is not False:
            raise ValueError("investigations require a genuine failed evaluated trace")
        case = self._get_case(parent_trace.scenario_id)
        self._assert_prompt_integrity(parent_trace, case.scenario)
        resolved_run_count = self._resolve_run_count(mode, run_count)
        investigation = Investigation(
            investigation_id=f"inv_{uuid4().hex}",
            parent_trace_id=parent_trace.trace_id,
            scenario_id=parent_trace.scenario_id,
            domain=parent_trace.domain,
            requested_model=parent_trace.requested_model,
            response_model=parent_trace.response_model,
            prompt_version=parent_trace.prompt_version,
            prompt_content_hash=parent_trace.prompt_content_hash,
            run_count=resolved_run_count,
            mode=mode if run_count is None else ReplayMode.CUSTOM,
            cache_policy="cache disabled during replay to measure repeated live executions",
            original_selected_action=parent_trace.selected_action,
            expected_action=case.scenario.expected_action,
            original_memory_snapshot=[
                memory.model_copy(deep=True) for memory in parent_trace.memory_snapshot
            ],
            created_at=datetime.now(timezone.utc),
        )
        self._write_investigation(investigation)
        self._write_replay_artifacts(investigation)
        return investigation

    def list_memories(self, investigation_id: str) -> list[AgentInputMemory]:
        investigation = self.load_investigation(investigation_id)
        return [memory.model_copy(deep=True) for memory in investigation.original_memory_snapshot]

    def replay_without_memory(self, investigation_id: str, memory_id: str) -> ReplayResult:
        return self._run_intervention(
            investigation_id=investigation_id,
            intervention=Intervention(
                intervention_type=InterventionType.REMOVE_MEMORY,
                target_memory_ids=[memory_id],
                reason=f"Remove {memory_id} from the snapshot",
            ),
        )

    def replay_with_memory_disabled(self, investigation_id: str, memory_id: str) -> ReplayResult:
        return self._run_intervention(
            investigation_id=investigation_id,
            intervention=Intervention(
                intervention_type=InterventionType.DISABLE_MEMORY,
                target_memory_ids=[memory_id],
                reason=f"Disable {memory_id} while preserving the rest of the snapshot",
            ),
        )

    def get_replay_results(self, investigation_id: str) -> list[ReplayResult]:
        return self.load_investigation(investigation_id).replay_results

    def load_investigation(self, investigation_id: str) -> Investigation:
        path = self._investigation_dir(investigation_id) / "investigation.json"
        if not path.exists():
            raise ValueError(f"unknown investigation: {investigation_id}")
        return Investigation.model_validate_json(path.read_text(encoding="utf-8"))

    def run_individual_ablation(self, investigation_id: str) -> Investigation:
        investigation = self.load_investigation(investigation_id)
        for memory in investigation.original_memory_snapshot:
            self.replay_without_memory(investigation_id, memory.memory_id)
            self.replay_with_memory_disabled(investigation_id, memory.memory_id)
        return self.load_investigation(investigation_id)

    def _run_intervention(
        self, *, investigation_id: str, intervention: Intervention
    ) -> ReplayResult:
        investigation = self.load_investigation(investigation_id)
        self._ensure_target_memory_exists(investigation, intervention.target_memory_ids[0])
        case = self._materialize_case(investigation)
        original_case = case.model_copy(deep=True)
        intervention_case = self._apply_intervention(case.model_copy(deep=True), intervention)

        original_traces = self._execute_batch(
            investigation=investigation,
            parent_trace_id=investigation.parent_trace_id,
            intervention=None,
            case=original_case,
            role="replay_original",
        )
        intervention_traces = self._execute_batch(
            investigation=investigation,
            parent_trace_id=investigation.parent_trace_id,
            intervention=intervention,
            case=intervention_case,
            role="replay_intervention",
        )

        original_batch = self._summarize_batch(original_traces)
        intervention_batch = self._summarize_batch(intervention_traces)
        low, high = wilson_score_interval(
            intervention_batch.successful_runs,
            intervention_batch.total_runs,
        )
        replay_result = ReplayResult(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            intervention=intervention,
            mode=investigation.mode,
            total_runs=intervention_batch.total_runs,
            successful_runs=intervention_batch.successful_runs,
            success_rate=intervention_batch.success_rate,
            confidence_interval_low=low,
            confidence_interval_high=high,
            original_successful_runs=original_batch.successful_runs,
            original_total_runs=original_batch.total_runs,
            original_success_rate=original_batch.success_rate,
            influence_delta=intervention_batch.success_rate - original_batch.success_rate,
            original_action_distribution=original_batch.action_distribution,
            intervention_action_distribution=intervention_batch.action_distribution,
            original_replay_stability=original_batch.replay_stability,
            intervention_replay_stability=intervention_batch.replay_stability,
            original_errors=original_batch.errors,
            intervention_errors=intervention_batch.errors,
            original_trace_ids=[trace.trace_id for trace in original_traces],
            intervention_trace_ids=[trace.trace_id for trace in intervention_traces],
        )

        updated = investigation.model_copy(deep=True)
        updated.replay_results = [
            result
            for result in updated.replay_results
            if not (
                result.intervention.intervention_type == intervention.intervention_type
                and result.intervention.target_memory_ids == intervention.target_memory_ids
            )
        ]
        updated.replay_results.append(replay_result)
        self._write_investigation(updated)
        self._write_replay_artifacts(updated)
        return replay_result

    def _execute_batch(
        self,
        *,
        investigation: Investigation,
        parent_trace_id: str,
        intervention: Intervention | None,
        case: BenchmarkCase,
        role: str,
    ) -> list[ExecutionTrace]:
        traces: list[ExecutionTrace] = []
        for _ in range(investigation.run_count):
            runner = self.runner_factory(self._get_trace(parent_trace_id))
            try:
                trace = runner.run_scenario(case.scenario, case.memories)
            except OpenAIRunnerError as exc:
                if exc.trace is None:
                    raise
                trace = exc.trace
            trace.parent_trace_id = parent_trace_id
            trace.investigation_id = investigation.investigation_id
            trace.replay_intervention = intervention
            trace.replay_role = role
            self.repository.save_trace(trace)
            self.session.commit()
            self._write_trace_artifact(investigation.investigation_id, trace)
            traces.append(trace)
        return traces

    def _summarize_batch(self, traces: list[ExecutionTrace]) -> ReplayBatch:
        action_counter = Counter(
            trace.selected_action for trace in traces if trace.selected_action is not None
        )
        evaluated = [trace for trace in traces if trace.passed is not None]
        successes = sum(1 for trace in evaluated if trace.passed)
        total = len(traces)
        total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for trace in traces:
            if trace.request_token_usage is None:
                continue
            for key in total_usage:
                total_usage[key] += trace.request_token_usage.get(key, 0)
        mode_count = max(action_counter.values(), default=0)
        stability = (mode_count / len(evaluated)) if evaluated else 0.0
        return ReplayBatch(
            traces=traces,
            successful_runs=successes,
            total_runs=total,
            success_rate=(successes / total) if total else 0.0,
            action_distribution=dict(sorted(action_counter.items())),
            replay_stability=stability,
            errors=[trace.error for trace in traces if trace.error is not None],
            token_usage=total_usage,
        )

    def _materialize_case(self, investigation: Investigation) -> BenchmarkCase:
        case = self._get_case(investigation.scenario_id).model_copy(deep=True)
        original_snapshot = {
            memory.memory_id: memory for memory in investigation.original_memory_snapshot
        }
        case.scenario.user_input = self._get_trace(investigation.parent_trace_id).user_input
        for memory in case.memories:
            snapshot = original_snapshot[memory.id]
            memory.entity_id = snapshot.entity_id
            memory.content = snapshot.content
            memory.source = snapshot.source
            memory.created_at = snapshot.created_at
            memory.valid_from = snapshot.valid_from
            memory.valid_until = snapshot.valid_until
            memory.status = snapshot.status
            memory.confidence = snapshot.confidence
            memory.retrieval_priority = snapshot.retrieval_priority
            memory.supersedes = list(snapshot.supersedes)
            memory.tags = list(snapshot.tags)
            memory.operational_metadata = snapshot.operational_metadata.copy()
        case.scenario.memory_ids = [
            memory.memory_id for memory in investigation.original_memory_snapshot
        ]
        return case

    def _apply_intervention(self, case: BenchmarkCase, intervention: Intervention) -> BenchmarkCase:
        target_memory_id = intervention.target_memory_ids[0]
        if intervention.intervention_type == InterventionType.REMOVE_MEMORY:
            case.memories = [memory for memory in case.memories if memory.id != target_memory_id]
            case.scenario.memory_ids = [
                memory_id for memory_id in case.scenario.memory_ids if memory_id != target_memory_id
            ]
            return case

        target_memory = next(memory for memory in case.memories if memory.id == target_memory_id)
        if intervention.intervention_type == InterventionType.DISABLE_MEMORY:
            target_memory.status = MemoryStatus.INVALID
            target_memory.operational_metadata = {
                **target_memory.operational_metadata,
                "disabled_for_replay": True,
            }
            return case
        if intervention.intervention_type == InterventionType.LOWER_RETRIEVAL_PRIORITY:
            target_memory.retrieval_priority = int(
                intervention.replacement_values.get("retrieval_priority", 0)
            )
            return case
        if intervention.intervention_type == InterventionType.MARK_SUPERSEDED:
            target_memory.status = MemoryStatus.SUPERSEDED
            superseding_id = str(
                intervention.replacement_values.get("superseded_by", "replay_override")
            )
            target_memory.supersedes = sorted(set([*target_memory.supersedes, superseding_id]))
            return case
        if intervention.intervention_type == InterventionType.REPLACE_MEMORY_WITH_CANDIDATE:
            candidate = intervention.replacement_values
            target_memory.content = str(candidate.get("content", target_memory.content))
            target_memory.source = str(candidate.get("source", target_memory.source))
            target_memory.confidence = float(candidate.get("confidence", target_memory.confidence))
            target_memory.retrieval_priority = int(
                candidate.get("retrieval_priority", target_memory.retrieval_priority)
            )
            return case
        raise ValueError(f"unsupported intervention type: {intervention.intervention_type}")

    def _build_runner_for_trace(self, parent_trace: ExecutionTrace) -> AgentRunner:
        if parent_trace.requested_model == FakeAgentRunner.model_name:
            return FakeAgentRunner()
        settings = replace(
            OpenAISettings.from_env(),
            model=parent_trace.requested_model,
            prompt_version=parent_trace.prompt_version,
            cache_enabled=False,
        )
        return OpenAIAgentRunner(settings=settings)

    def _assert_prompt_integrity(self, trace: ExecutionTrace, scenario: AgentScenario) -> None:
        if trace.prompt_content_hash is None:
            return
        prompt = load_domain_prompt(scenario.domain, trace.prompt_version, scenario.allowed_actions)
        prompt_hash = _hash_prompt(prompt)
        if prompt_hash != trace.prompt_content_hash:
            raise ValueError("current prompt content does not match the original failed trace")

    def _resolve_run_count(self, mode: ReplayMode, run_count: int | None) -> int:
        if run_count is not None:
            return run_count
        if mode == ReplayMode.FAST:
            return FAST_RUNS
        if mode == ReplayMode.DEEP:
            return DEEP_RUNS
        raise ValueError("custom mode requires an explicit run count")

    def _ensure_target_memory_exists(self, investigation: Investigation, memory_id: str) -> None:
        if memory_id not in {memory.memory_id for memory in investigation.original_memory_snapshot}:
            raise ValueError(
                f"memory {memory_id} is not part of investigation {investigation.investigation_id}"
            )

    def _get_case(self, scenario_id: str) -> BenchmarkCase:
        try:
            return self.case_lookup[scenario_id]
        except KeyError as exc:
            raise ValueError(f"unknown scenario: {scenario_id}") from exc

    def _get_trace(self, trace_id: str) -> ExecutionTrace:
        trace = self.repository.get_trace(trace_id)
        if trace is None:
            raise ValueError(f"unknown trace: {trace_id}")
        return trace

    def _investigation_dir(self, investigation_id: str) -> Path:
        return self.artifacts_dir / "investigations" / investigation_id

    def _write_investigation(self, investigation: Investigation) -> None:
        path = self._investigation_dir(investigation.investigation_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "investigation.json").write_text(
            investigation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _write_trace_artifact(self, investigation_id: str, trace: ExecutionTrace) -> None:
        trace_dir = self._investigation_dir(investigation_id) / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{trace.trace_id}.json"
        (trace_dir / file_name).write_text(trace.model_dump_json(indent=2), encoding="utf-8")

    def _write_replay_artifacts(self, investigation: Investigation) -> None:
        investigation_dir = self._investigation_dir(investigation.investigation_id)
        (investigation_dir / "individual-replay.json").write_text(
            json.dumps(
                {
                    "investigation": investigation.model_dump(mode="json"),
                    "total_api_usage": self._aggregate_usage(investigation),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (investigation_dir / "individual-replay.md").write_text(
            self._render_markdown(investigation),
            encoding="utf-8",
        )

    def _render_markdown(self, investigation: Investigation) -> str:
        lines = [
            "# Individual Memory Replay",
            "",
            f"- Investigation ID: `{investigation.investigation_id}`",
            f"- Parent trace: `{investigation.parent_trace_id}`",
            f"- Scenario: `{investigation.scenario_id}`",
            f"- Expected action: `{investigation.expected_action}`",
            f"- Original action: `{investigation.original_selected_action}`",
            f"- Replay mode: `{investigation.mode.value}`",
            f"- Run count: `{investigation.run_count}`",
            f"- Cache policy: {investigation.cache_policy}",
            "",
            "## Results",
            "",
        ]
        if not investigation.replay_results:
            lines.append("- No replay results yet")
        else:
            for result in investigation.replay_results:
                lines.append(
                    f"- `{result.intervention.intervention_type.value}` on "
                    f"`{result.intervention.target_memory_ids[0]}`: "
                    f"before={result.original_action_distribution} "
                    f"after={result.intervention_action_distribution} "
                    f"delta={result.influence_delta:.3f}"
                )
        return "\n".join(lines) + "\n"

    def _aggregate_usage(self, investigation: Investigation) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for result in investigation.replay_results:
            for trace_id in [*result.original_trace_ids, *result.intervention_trace_ids]:
                trace = self._get_trace(trace_id)
                if trace.request_token_usage is None:
                    continue
                for key in totals:
                    totals[key] += trace.request_token_usage.get(key, 0)
        return totals


def _hash_prompt(prompt: str) -> str:
    import hashlib

    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
