from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import combinations
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
    DecisionSupportAudit,
    ExecutionTrace,
    Intervention,
    InterventionType,
    Investigation,
    MemoryControlResult,
    MemoryControlsArtifact,
    MemoryControlType,
    MemoryDependenceClassification,
    MemoryStatus,
    PairEvidenceClassification,
    PairSelectionRecord,
    PairwiseReplayArtifact,
    PairwiseReplayResult,
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
    evaluated_runs: int
    success_rate: float
    action_distribution: dict[str, int]
    replay_stability: float
    errors: list[TraceErrorDetails]
    token_usage: dict[str, int]
    latency_ms: int


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

    def generate_ranked_pairs(
        self,
        investigation_id: str,
        *,
        max_memories: int = 5,
    ) -> PairSelectionRecord:
        investigation = self.load_investigation(investigation_id)
        ranking_path = self._investigation_dir(investigation_id) / "suspicion-ranking.json"
        ranking_source = "investigation_snapshot"
        ranking_version: str | None = None
        ranking_snapshot_hash: str | None = None
        if ranking_path.exists():
            ranking_payload = json.loads(ranking_path.read_text(encoding="utf-8"))
            selected_memory_ids = [
                memory["memory_id"] for memory in ranking_payload["memories"][:max_memories]
            ]
            ranking_source = "suspicion-ranking.json"
            ranking_version = ranking_payload["metadata"].get("semantic_analysis_prompt_version")
            ranking_snapshot_hash = ranking_payload["metadata"].get("memory_snapshot_hash")
        else:
            selected_memory_ids = [
                memory.memory_id for memory in investigation.original_memory_snapshot[:max_memories]
            ]
        generated_pairs = [
            [left, right] for left, right in combinations(sorted(selected_memory_ids), 2)
        ]
        return PairSelectionRecord(
            selected_memory_ids=selected_memory_ids,
            generated_pairs=generated_pairs,
            ranking_source=ranking_source,
            ranking_version=ranking_version,
            ranking_snapshot_hash=ranking_snapshot_hash,
            created_at=datetime.now(timezone.utc),
        )

    def replay_pairwise(
        self,
        investigation_id: str,
        *,
        memory_a: str | None = None,
        memory_b: str | None = None,
        all_pairs: bool = False,
        shared_baseline_runs: bool = True,
        fresh_baseline_per_pair: bool = False,
    ) -> PairwiseReplayArtifact:
        investigation = self.load_investigation(investigation_id)
        pair_selection = self.generate_ranked_pairs(investigation_id)
        if memory_a is not None and memory_b is not None:
            pair_targets = [[*sorted([memory_a, memory_b])]]
        elif all_pairs:
            pair_targets = pair_selection.generated_pairs
        else:
            pair_targets = pair_selection.generated_pairs

        original_case = self._materialize_case(investigation)
        shared_baseline = None
        shared_trace_ids: list[str] = []
        if shared_baseline_runs and not fresh_baseline_per_pair:
            shared_traces = self._execute_batch(
                investigation=investigation,
                parent_trace_id=investigation.parent_trace_id,
                intervention=None,
                case=original_case.model_copy(deep=True),
                role="pairwise_shared_baseline",
            )
            shared_baseline = self._summarize_batch(shared_traces)
            shared_trace_ids = [trace.trace_id for trace in shared_traces]

        pair_results: list[PairwiseReplayResult] = []
        for target_pair in pair_targets:
            self._ensure_target_memory_exists(investigation, target_pair[0])
            self._ensure_target_memory_exists(investigation, target_pair[1])
            for intervention_type in (
                InterventionType.REMOVE_MEMORIES,
                InterventionType.DISABLE_MEMORIES,
            ):
                pair_results.append(
                    self._run_pair_intervention(
                        investigation=investigation,
                        target_memory_ids=target_pair,
                        intervention_type=intervention_type,
                        shared_baseline=shared_baseline,
                        shared_trace_ids=shared_trace_ids,
                        shared_baseline_runs=shared_baseline_runs,
                        fresh_baseline_per_pair=fresh_baseline_per_pair,
                    )
                )

        artifact = PairwiseReplayArtifact(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            original_snapshot_hash=self._snapshot_hash(investigation.original_memory_snapshot),
            pair_selection=pair_selection,
            shared_baseline_runs=shared_baseline_runs,
            fresh_baseline_per_pair=fresh_baseline_per_pair,
            individual_replay_evidence=investigation.replay_results,
            pair_results=self._rank_pair_results(pair_results),
            memory_dependence_classification=self.classify_memory_dependence(
                investigation_id,
                pair_results=pair_results,
            ),
            model=investigation.requested_model,
            prompt_version=investigation.prompt_version,
            api_usage=self._aggregate_trace_usage(pair_results),
            git_commit_hash=self._git_commit_hash(),
            created_at=datetime.now(timezone.utc),
        )
        self._write_pairwise_artifacts(artifact)
        return artifact

    def run_no_memory_control(self, investigation_id: str) -> MemoryControlResult:
        investigation = self.load_investigation(investigation_id)
        return self._run_control(
            investigation=investigation,
            control_type=MemoryControlType.NO_MEMORY,
            target_memory_id=None,
        )

    def run_isolate_memory(self, investigation_id: str, memory_id: str) -> MemoryControlResult:
        investigation = self.load_investigation(investigation_id)
        self._ensure_target_memory_exists(investigation, memory_id)
        return self._run_control(
            investigation=investigation,
            control_type=MemoryControlType.ISOLATE_MEMORY,
            target_memory_id=memory_id,
        )

    def run_all_isolation_controls(self, investigation_id: str) -> list[MemoryControlResult]:
        investigation = self.load_investigation(investigation_id)
        return [
            self.run_isolate_memory(investigation_id, memory.memory_id)
            for memory in investigation.original_memory_snapshot
        ]

    def export_memory_controls(self, investigation_id: str) -> MemoryControlsArtifact:
        investigation = self.load_investigation(investigation_id)
        no_memory = self.run_no_memory_control(investigation_id)
        isolation_controls = self.run_all_isolation_controls(investigation_id)
        artifact = MemoryControlsArtifact(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            original_snapshot_hash=self._snapshot_hash(investigation.original_memory_snapshot),
            no_memory_control=no_memory,
            isolation_controls=isolation_controls,
            memory_dependence_classification=self.classify_memory_dependence(
                investigation_id,
                control_results=[no_memory, *isolation_controls],
            ),
            model=investigation.requested_model,
            prompt_version=investigation.prompt_version,
            api_usage=self._aggregate_control_usage([no_memory, *isolation_controls]),
            git_commit_hash=self._git_commit_hash(),
            created_at=datetime.now(timezone.utc),
        )
        self._write_control_artifacts(artifact)
        return artifact

    def classify_memory_dependence(
        self,
        investigation_id: str,
        *,
        pair_results: list[PairwiseReplayResult] | None = None,
        control_results: list[MemoryControlResult] | None = None,
    ) -> MemoryDependenceClassification:
        investigation = self.load_investigation(investigation_id)
        individual_strong = any(
            abs(result.influence_delta) >= 0.5
            and result.original_action_distribution != result.intervention_action_distribution
            for result in investigation.replay_results
        )
        if individual_strong:
            return MemoryDependenceClassification.INDIVIDUAL_MEMORY_DEPENDENT
        pair_results = pair_results or self._load_pair_results_if_present(investigation_id)
        if any(
            result.evidence_classification == PairEvidenceClassification.INTERACTION_SUPPORTED
            for result in pair_results
        ):
            return MemoryDependenceClassification.PAIRWISE_MEMORY_DEPENDENT
        control_results = control_results or self._load_controls_if_present(investigation_id)
        no_memory = next(
            (
                result
                for result in control_results
                if result.control_type == MemoryControlType.NO_MEMORY
            ),
            None,
        )
        if no_memory is None:
            return MemoryDependenceClassification.INCONCLUSIVE
        original_top_action = (
            self._dominant_action_from_results(investigation.replay_results)
            or investigation.original_selected_action
        )
        control_top_action = self._dominant_action(no_memory.control_action_distribution)
        if control_top_action == original_top_action and control_top_action is not None:
            return MemoryDependenceClassification.LIKELY_MEMORY_INDEPENDENT
        if control_top_action != original_top_action and not pair_results:
            return MemoryDependenceClassification.DISTRIBUTED_MEMORY_DEPENDENT
        if control_top_action != original_top_action:
            return MemoryDependenceClassification.DISTRIBUTED_MEMORY_DEPENDENT
        return MemoryDependenceClassification.INCONCLUSIVE

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

    def _run_pair_intervention(
        self,
        *,
        investigation: Investigation,
        target_memory_ids: list[str],
        intervention_type: InterventionType,
        shared_baseline: ReplayBatch | None,
        shared_trace_ids: list[str],
        shared_baseline_runs: bool,
        fresh_baseline_per_pair: bool,
    ) -> PairwiseReplayResult:
        case = self._materialize_case(investigation)
        intervention = self._build_intervention(
            investigation=investigation,
            case=case,
            intervention_type=intervention_type,
            target_memory_ids=target_memory_ids,
            reason=f"{intervention_type.value} on {' + '.join(target_memory_ids)}",
        )
        intervention_case = self._apply_intervention(case.model_copy(deep=True), intervention)

        if shared_baseline is None or fresh_baseline_per_pair:
            original_traces = self._execute_batch(
                investigation=investigation,
                parent_trace_id=investigation.parent_trace_id,
                intervention=None,
                case=case.model_copy(deep=True),
                role="pairwise_pair_baseline",
            )
            original_batch = self._summarize_batch(original_traces)
            original_trace_ids = [trace.trace_id for trace in original_traces]
        else:
            original_batch = shared_baseline
            original_trace_ids = list(shared_trace_ids)

        intervention_traces = self._execute_batch(
            investigation=investigation,
            parent_trace_id=investigation.parent_trace_id,
            intervention=intervention,
            case=intervention_case,
            role="pairwise_intervention",
        )
        intervention_batch = self._summarize_batch(intervention_traces)
        low, high = wilson_score_interval(
            intervention_batch.successful_runs,
            intervention_batch.evaluated_runs,
        )
        combined_influence = intervention_batch.success_rate - original_batch.success_rate
        individual_influences = self._lookup_individual_influences(
            investigation.replay_results,
            target_memory_ids,
        )
        max_individual = max(
            (abs(value) for value in individual_influences.values()),
            default=0.0,
        )
        interaction_score = combined_influence - max_individual
        interaction_synergy = combined_influence - sum(
            abs(value) for value in individual_influences.values()
        )
        support_validity = self._audit_support(
            case=intervention_case,
            selected_action=self._dominant_action(intervention_batch.action_distribution),
            expected_action=investigation.expected_action,
        )
        return PairwiseReplayResult(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            intervention=intervention,
            shared_baseline_runs=shared_baseline_runs,
            fresh_baseline_per_pair=fresh_baseline_per_pair,
            original_successful_runs=original_batch.successful_runs,
            original_total_evaluated_runs=original_batch.evaluated_runs,
            original_success_rate=original_batch.success_rate,
            original_action_distribution=original_batch.action_distribution,
            individual_influences=individual_influences,
            combined_successful_runs=intervention_batch.successful_runs,
            combined_total_evaluated_runs=intervention_batch.evaluated_runs,
            combined_success_rate=intervention_batch.success_rate,
            combined_action_distribution=intervention_batch.action_distribution,
            combined_influence=combined_influence,
            interaction_score=interaction_score,
            interaction_synergy=interaction_synergy,
            confidence_interval_low=low,
            confidence_interval_high=high,
            replay_stability=intervention_batch.replay_stability,
            infrastructure_error_count=len(intervention_batch.errors),
            token_usage=intervention_batch.token_usage,
            latency_ms=intervention_batch.latency_ms,
            support_validity=support_validity,
            evidence_classification=self._classify_pair_evidence(
                combined_influence=combined_influence,
                interaction_score=interaction_score,
                interaction_synergy=interaction_synergy,
                action_changed=(
                    original_batch.action_distribution != intervention_batch.action_distribution
                ),
                max_individual_influence=max_individual,
                infrastructure_error_count=len(intervention_batch.errors),
            ),
            original_trace_ids=original_trace_ids,
            intervention_trace_ids=[trace.trace_id for trace in intervention_traces],
        )

    def _run_control(
        self,
        *,
        investigation: Investigation,
        control_type: MemoryControlType,
        target_memory_id: str | None,
    ) -> MemoryControlResult:
        case = self._materialize_case(investigation)
        original_traces = self._execute_batch(
            investigation=investigation,
            parent_trace_id=investigation.parent_trace_id,
            intervention=None,
            case=case.model_copy(deep=True),
            role=f"{control_type.value}_baseline",
        )
        original_batch = self._summarize_batch(original_traces)
        if control_type == MemoryControlType.NO_MEMORY:
            intervention_type = InterventionType.REMOVE_ALL_MEMORIES
            target_ids = [memory.memory_id for memory in investigation.original_memory_snapshot]
            reason = "Remove all memories from the snapshot"
        else:
            intervention_type = InterventionType.ISOLATE_MEMORY
            target_ids = [target_memory_id] if target_memory_id is not None else []
            reason = f"Retain only {target_memory_id} in the snapshot"
        intervention = self._build_intervention(
            investigation=investigation,
            case=case,
            intervention_type=intervention_type,
            target_memory_ids=target_ids,
            reason=reason,
        )
        control_case = self._apply_intervention(case.model_copy(deep=True), intervention)
        control_traces = self._execute_batch(
            investigation=investigation,
            parent_trace_id=investigation.parent_trace_id,
            intervention=intervention,
            case=control_case,
            role=f"{control_type.value}_intervention",
        )
        control_batch = self._summarize_batch(control_traces)
        support_validity = self._audit_support(
            case=control_case,
            selected_action=self._dominant_action(control_batch.action_distribution),
            expected_action=investigation.expected_action,
        )
        return MemoryControlResult(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            control_type=control_type,
            target_memory_id=target_memory_id,
            intervention=intervention,
            original_successful_runs=original_batch.successful_runs,
            original_total_evaluated_runs=original_batch.evaluated_runs,
            original_success_rate=original_batch.success_rate,
            original_action_distribution=original_batch.action_distribution,
            control_successful_runs=control_batch.successful_runs,
            control_total_evaluated_runs=control_batch.evaluated_runs,
            control_success_rate=control_batch.success_rate,
            control_action_distribution=control_batch.action_distribution,
            replay_stability=control_batch.replay_stability,
            infrastructure_error_count=len(control_batch.errors),
            token_usage=control_batch.token_usage,
            latency_ms=control_batch.latency_ms,
            support_validity=support_validity,
            original_trace_ids=[trace.trace_id for trace in original_traces],
            control_trace_ids=[trace.trace_id for trace in control_traces],
        )

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
            evaluated_runs=len(evaluated),
            success_rate=(successes / total) if total else 0.0,
            action_distribution=dict(sorted(action_counter.items())),
            replay_stability=stability,
            errors=[trace.error for trace in traces if trace.error is not None],
            token_usage=total_usage,
            latency_ms=sum(trace.latency_ms for trace in traces),
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
        target_memory_id = (
            intervention.target_memory_ids[0] if intervention.target_memory_ids else ""
        )
        if intervention.intervention_type == InterventionType.REMOVE_MEMORY:
            case.memories = [memory for memory in case.memories if memory.id != target_memory_id]
            case.scenario.memory_ids = [
                memory_id for memory_id in case.scenario.memory_ids if memory_id != target_memory_id
            ]
            return case
        if intervention.intervention_type == InterventionType.REMOVE_MEMORIES:
            target_set = set(intervention.target_memory_ids)
            case.memories = [memory for memory in case.memories if memory.id not in target_set]
            case.scenario.memory_ids = [
                memory_id for memory_id in case.scenario.memory_ids if memory_id not in target_set
            ]
            return case
        if intervention.intervention_type == InterventionType.REMOVE_ALL_MEMORIES:
            case.memories = []
            case.scenario.memory_ids = []
            return case
        if intervention.intervention_type == InterventionType.ISOLATE_MEMORY:
            target_set = set(intervention.target_memory_ids)
            case.memories = [memory for memory in case.memories if memory.id in target_set]
            case.scenario.memory_ids = [
                memory_id for memory_id in case.scenario.memory_ids if memory_id in target_set
            ]
            return case

        if intervention.intervention_type == InterventionType.DISABLE_MEMORIES:
            target_set = set(intervention.target_memory_ids)
            for memory in case.memories:
                if memory.id in target_set:
                    memory.status = MemoryStatus.INVALID
                    memory.operational_metadata = {
                        **memory.operational_metadata,
                        "disabled_for_replay": True,
                    }
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

    def _write_pairwise_artifacts(self, artifact: PairwiseReplayArtifact) -> None:
        investigation_dir = self._investigation_dir(artifact.investigation_id)
        (investigation_dir / "pairwise-replay.json").write_text(
            artifact.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (investigation_dir / "pairwise-replay.md").write_text(
            self._render_pairwise_markdown(artifact),
            encoding="utf-8",
        )

    def _write_control_artifacts(self, artifact: MemoryControlsArtifact) -> None:
        investigation_dir = self._investigation_dir(artifact.investigation_id)
        (investigation_dir / "memory-controls.json").write_text(
            artifact.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (investigation_dir / "memory-controls.md").write_text(
            self._render_controls_markdown(artifact),
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

    def _build_intervention(
        self,
        *,
        investigation: Investigation,
        case: BenchmarkCase,
        intervention_type: InterventionType,
        target_memory_ids: list[str],
        reason: str,
    ) -> Intervention:
        before_states = {
            memory.id: memory.to_agent_input().model_dump(mode="json")
            for memory in case.memories
            if memory.id in target_memory_ids
        }
        mutated_case = self._apply_intervention(
            case.model_copy(deep=True),
            Intervention(
                intervention_type=intervention_type,
                target_memory_ids=target_memory_ids,
                reason=reason,
            ),
        )
        after_states = {
            memory.id: memory.to_agent_input().model_dump(mode="json")
            for memory in mutated_case.memories
            if memory.id in target_memory_ids
        }
        return Intervention(
            intervention_type=intervention_type,
            target_memory_ids=target_memory_ids,
            reason=reason,
            before_states=before_states,
            after_states=after_states,
            unchanged_input_hash=self._snapshot_hash(
                [
                    memory
                    for memory in investigation.original_memory_snapshot
                    if memory.memory_id not in target_memory_ids
                ]
            ),
            model=investigation.requested_model,
            prompt_version=investigation.prompt_version,
            inference_configuration=self._inference_configuration(),
            created_at=datetime.now(timezone.utc),
        )

    def _lookup_individual_influences(
        self,
        replay_results: list[ReplayResult],
        target_memory_ids: list[str],
    ) -> dict[str, float]:
        influences: dict[str, float] = {}
        for memory_id in target_memory_ids:
            matching = [
                result
                for result in replay_results
                if result.intervention.target_memory_ids == [memory_id]
                and result.intervention.intervention_type
                in {InterventionType.REMOVE_MEMORY, InterventionType.DISABLE_MEMORY}
            ]
            influences[memory_id] = max(
                (abs(result.influence_delta) for result in matching),
                default=0.0,
            )
        return influences

    def _classify_pair_evidence(
        self,
        *,
        combined_influence: float,
        interaction_score: float,
        interaction_synergy: float,
        action_changed: bool,
        max_individual_influence: float,
        infrastructure_error_count: int,
    ) -> PairEvidenceClassification:
        if infrastructure_error_count > 0 and not action_changed:
            return PairEvidenceClassification.INCONCLUSIVE
        if abs(combined_influence) < 0.01 and not action_changed:
            return PairEvidenceClassification.NO_OBSERVED_PAIRWISE_INFLUENCE
        if combined_influence < max_individual_influence - 0.1:
            return PairEvidenceClassification.NEGATIVE_INTERACTION
        if max_individual_influence >= 0.5 and abs(interaction_score) < 0.1:
            return PairEvidenceClassification.DOMINATED_BY_ONE_MEMORY
        if max_individual_influence > 0 and abs(interaction_synergy) < 0.1:
            return PairEvidenceClassification.REDUNDANT_PAIR
        if interaction_score > 0 and action_changed:
            return PairEvidenceClassification.INTERACTION_SUPPORTED
        return PairEvidenceClassification.NO_OBSERVED_PAIRWISE_INFLUENCE

    def _audit_support(
        self,
        *,
        case: BenchmarkCase,
        selected_action: str | None,
        expected_action: str,
    ) -> DecisionSupportAudit:
        if selected_action is None:
            return DecisionSupportAudit(
                outcome_correct=False,
                decision_still_supported=False,
                support_explanation="No evaluated action was available for the intervention.",
                requires_human_review=True,
            )
        active_policy = any(
            memory.status == MemoryStatus.ACTIVE
            and (
                str(memory.operational_metadata.get("memory_role", "")).endswith("policy")
                or str(memory.operational_metadata.get("memory_role", "")) == "policy"
            )
            for memory in case.memories
        )
        active_evidence = any(
            memory.status == MemoryStatus.ACTIVE
            and str(memory.operational_metadata.get("memory_role", "")) == "evidence"
            for memory in case.memories
        )
        outcome_correct = selected_action == expected_action
        if not case.memories:
            return DecisionSupportAudit(
                outcome_correct=outcome_correct,
                decision_still_supported=False,
                support_explanation=(
                    "The intervention removed all memories, so the resulting decision is "
                    "unsupported by memory evidence."
                ),
                requires_human_review=True,
            )
        if outcome_correct and active_policy and active_evidence:
            return DecisionSupportAudit(
                outcome_correct=True,
                decision_still_supported=True,
                support_explanation=(
                    "The expected action remains supported by active policy and evidence "
                    "in the remaining snapshot."
                ),
                requires_human_review=False,
            )
        if outcome_correct:
            return DecisionSupportAudit(
                outcome_correct=True,
                decision_still_supported=False,
                support_explanation=(
                    "The intervention changed behavior, but the remaining snapshot no "
                    "longer contains enough active policy and evidence to support the "
                    "expected action confidently."
                ),
                requires_human_review=True,
            )
        return DecisionSupportAudit(
            outcome_correct=False,
            decision_still_supported=False,
            support_explanation="The intervention did not reach the expected action.",
            requires_human_review=False,
        )

    def _rank_pair_results(
        self,
        pair_results: list[PairwiseReplayResult],
    ) -> list[PairwiseReplayResult]:
        return sorted(
            pair_results,
            key=lambda result: (
                result.combined_influence,
                result.interaction_score,
                result.replay_stability,
                -result.infrastructure_error_count,
                int(result.support_validity.decision_still_supported),
            ),
            reverse=True,
        )

    def _aggregate_trace_usage(
        self,
        pair_results: list[PairwiseReplayResult],
    ) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for result in pair_results:
            for key in totals:
                totals[key] += result.token_usage.get(key, 0)
        return totals

    def _aggregate_control_usage(
        self,
        control_results: list[MemoryControlResult],
    ) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for result in control_results:
            for key in totals:
                totals[key] += result.token_usage.get(key, 0)
        return totals

    def _snapshot_hash(self, snapshot: list[AgentInputMemory]) -> str:
        return hashlib.sha256(
            json.dumps(
                [memory.model_dump(mode="json") for memory in snapshot],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _inference_configuration(self) -> dict[str, str | bool | float | int | None]:
        settings = OpenAISettings.from_env()
        return {
            "model": settings.model,
            "timeout_seconds": settings.timeout_seconds,
            "max_retries": settings.max_retries,
            "cache_enabled": settings.cache_enabled,
            "prompt_version": settings.prompt_version,
            "reasoning_effort": settings.reasoning_effort,
            "verbosity": settings.verbosity,
        }

    def _git_commit_hash(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3],
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    def _dominant_action(self, action_distribution: dict[str, int]) -> str | None:
        if not action_distribution:
            return None
        return max(
            sorted(action_distribution.items()),
            key=lambda item: item[1],
        )[0]

    def _dominant_action_from_results(self, replay_results: list[ReplayResult]) -> str | None:
        if not replay_results:
            return None
        return self._dominant_action(replay_results[0].original_action_distribution)

    def _render_pairwise_markdown(self, artifact: PairwiseReplayArtifact) -> str:
        lines = [
            "# Pairwise Replay",
            "",
            f"- Investigation ID: `{artifact.investigation_id}`",
            f"- Scenario: `{artifact.scenario_id}`",
            (
                f"- Memory-dependence classification: "
                f"`{artifact.memory_dependence_classification.value}`"
            ),
            f"- Shared baseline runs: `{artifact.shared_baseline_runs}`",
            "",
            "## Pair Results",
            "",
        ]
        for result in artifact.pair_results:
            lines.append(
                f"- `{', '.join(result.intervention.target_memory_ids)}` "
                f"via `{result.intervention.intervention_type.value}`: "
                f"combined={result.combined_influence:.3f}, "
                f"interaction={result.interaction_score:.3f}, "
                f"synergy={result.interaction_synergy:.3f}, "
                f"classification={result.evidence_classification.value}, "
                f"supported={result.support_validity.decision_still_supported}"
            )
        return "\n".join(lines) + "\n"

    def _render_controls_markdown(self, artifact: MemoryControlsArtifact) -> str:
        lines = [
            "# Memory Controls",
            "",
            f"- Investigation ID: `{artifact.investigation_id}`",
            f"- Scenario: `{artifact.scenario_id}`",
            (
                f"- Memory-dependence classification: "
                f"`{artifact.memory_dependence_classification.value}`"
            ),
            "",
            "## Controls",
            "",
            (
                f"- `no-memory`: actions={artifact.no_memory_control.control_action_distribution}, "
                f"supported={artifact.no_memory_control.support_validity.decision_still_supported}"
            ),
        ]
        for result in artifact.isolation_controls:
            lines.append(
                f"- `only {result.target_memory_id}`: "
                f"actions={result.control_action_distribution}, "
                f"supported={result.support_validity.decision_still_supported}"
            )
        return "\n".join(lines) + "\n"

    def _load_pair_results_if_present(
        self,
        investigation_id: str,
    ) -> list[PairwiseReplayResult]:
        path = self._investigation_dir(investigation_id) / "pairwise-replay.json"
        if not path.exists():
            return []
        artifact = PairwiseReplayArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        return artifact.pair_results

    def _load_controls_if_present(
        self,
        investigation_id: str,
    ) -> list[MemoryControlResult]:
        path = self._investigation_dir(investigation_id) / "memory-controls.json"
        if not path.exists():
            return []
        artifact = MemoryControlsArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        return [artifact.no_memory_control, *artifact.isolation_controls]


def _hash_prompt(prompt: str) -> str:
    import hashlib

    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
