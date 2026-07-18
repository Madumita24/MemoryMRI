from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from memory_mri.analysis.models import (
    AnalysisArtifactMetadata,
    ContradictionAnalysisArtifact,
    ContradictionAnalysisInput,
    ContradictionPairInput,
    DeterministicPairObservation,
    InvestigationSummary,
    MemoryPriorityResult,
    PairAnalysisResult,
    ReplayComparisonClassification,
    SemanticMemoryAnalysis,
    SemanticPairAnalysis,
    SuspicionAnalysisInput,
    SuspicionRankingArtifact,
)
from memory_mri.analysis.scoring import (
    build_deterministic_pair_observations,
    score_memories,
    summarize_replay_evidence,
)
from memory_mri.analysis.semantic import InvestigationSemanticAnalyzer
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings, SuspicionScoringConfig
from memory_mri.db.session import create_sqlite_session
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import ExecutionTrace, Investigation


class InvestigationAnalysisEngine:
    def __init__(
        self,
        *,
        database_url: str,
        artifacts_dir: Path,
        settings: OpenAISettings | None = None,
        prompt_settings: SemanticAnalysisSettings | None = None,
        scoring_config: SuspicionScoringConfig | None = None,
        semantic_analyzer: InvestigationSemanticAnalyzer | None = None,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.artifacts_dir = artifacts_dir
        self.settings = settings or OpenAISettings.from_env()
        self.prompt_settings = prompt_settings or SemanticAnalysisSettings.from_env()
        self.scoring_config = scoring_config or SuspicionScoringConfig.from_env()
        self.semantic_analyzer = semantic_analyzer or InvestigationSemanticAnalyzer(
            settings=self.settings,
            prompt_settings=self.prompt_settings,
        )

    def load_investigation(self, investigation_id: str) -> Investigation:
        path = self._investigation_dir(investigation_id) / "investigation.json"
        if not path.exists():
            raise ValueError(f"unknown investigation: {investigation_id}")
        return Investigation.model_validate_json(path.read_text(encoding="utf-8"))

    def rank_memories(self, investigation_id: str) -> SuspicionRankingArtifact:
        investigation = self.load_investigation(investigation_id)
        parent_trace = self._get_trace(investigation.parent_trace_id)
        pair_observations = build_deterministic_pair_observations(
            investigation.original_memory_snapshot
        )
        deterministic_results = score_memories(
            memories=investigation.original_memory_snapshot,
            cited_memory_ids=parent_trace.cited_memory_ids,
            pair_observations=pair_observations,
            config=self.scoring_config,
        )
        semantic_input = SuspicionAnalysisInput(
            scenario_id=investigation.scenario_id,
            domain=investigation.domain,
            user_request=parent_trace.user_input,
            allowed_actions=parent_trace.agent_input.allowed_actions,
            original_selected_action=parent_trace.selected_action,
            concise_original_rationale=parent_trace.concise_rationale,
            memories=investigation.original_memory_snapshot,
        )
        semantic_result = self.semantic_analyzer.analyze_memory_suspicion(semantic_input)
        semantic_analyses = cast(list[SemanticMemoryAnalysis], semantic_result.analyses)
        semantic_by_id = {analysis.memory_id: analysis for analysis in semantic_analyses}

        ranked_memories: list[MemoryPriorityResult] = []
        for deterministic_result in deterministic_results:
            semantic_analysis = semantic_by_id[deterministic_result.memory_id]
            replay_evidence, comparison = summarize_replay_evidence(
                memory_id=deterministic_result.memory_id,
                replay_results=investigation.replay_results,
                suspicion_score=max(
                    deterministic_result.deterministic_score,
                    semantic_analysis.semantic_suspicion_score,
                ),
            )
            prioritization_score = min(
                1.0,
                (
                    self.scoring_config.prioritization_weight_deterministic
                    * deterministic_result.deterministic_score
                )
                + (
                    self.scoring_config.prioritization_weight_semantic
                    * semantic_analysis.semantic_suspicion_score
                ),
            )
            ranked_memories.append(
                MemoryPriorityResult(
                    memory_id=deterministic_result.memory_id,
                    deterministic_score=deterministic_result.deterministic_score,
                    semantic_score=semantic_analysis.semantic_suspicion_score,
                    prioritization_score=prioritization_score,
                    metadata_observations=deterministic_result.metadata_observations,
                    semantic_hypothesis=semantic_analysis,
                    replay_supported_evidence=replay_evidence,
                    comparison_classification=comparison,
                    deterministic_reasons=[
                        observation.concise_reason
                        for observation in deterministic_result.metadata_observations
                        if observation.signal_present
                    ],
                    semantic_reason=semantic_analysis.concise_reason,
                )
            )

        ranked_memories.sort(
            key=lambda result: (result.prioritization_score, result.memory_id),
            reverse=True,
        )
        artifact = SuspicionRankingArtifact(
            metadata=self._build_metadata(
                investigation=investigation,
                response_model=semantic_result.response_model,
                prompt_version=self.prompt_settings.suspicion_prompt_version,
                prompt_hash=semantic_result.prompt_hash,
                api_usage=semantic_result.usage,
            ),
            memories=ranked_memories,
            summary=self._build_ranking_summary(ranked_memories, pair_observations),
        )
        self._write_json(
            self._investigation_dir(investigation_id) / "suspicion-ranking.json",
            artifact.model_dump(mode="json"),
        )
        self._write_markdown(
            self._investigation_dir(investigation_id) / "suspicion-ranking.md",
            self._render_ranking_markdown(artifact),
        )
        return artifact

    def analyze_contradictions(self, investigation_id: str) -> ContradictionAnalysisArtifact:
        investigation = self.load_investigation(investigation_id)
        parent_trace = self._get_trace(investigation.parent_trace_id)
        deterministic_pairs = build_deterministic_pair_observations(
            investigation.original_memory_snapshot
        )
        pair_inputs = [
            ContradictionPairInput(
                memory_a_id=pair.memory_a_id,
                memory_b_id=pair.memory_b_id,
            )
            for pair in deterministic_pairs
        ]
        semantic_input = ContradictionAnalysisInput(
            scenario_id=investigation.scenario_id,
            domain=investigation.domain,
            user_request=parent_trace.user_input,
            allowed_actions=parent_trace.agent_input.allowed_actions,
            original_selected_action=parent_trace.selected_action,
            concise_original_rationale=parent_trace.concise_rationale,
            memories=investigation.original_memory_snapshot,
            pairs=pair_inputs,
        )
        semantic_result = self.semantic_analyzer.analyze_pair_relationships(semantic_input)
        semantic_pairs_list = cast(list[SemanticPairAnalysis], semantic_result.analyses)
        semantic_pairs = {
            (analysis.memory_a_id, analysis.memory_b_id): analysis
            for analysis in semantic_pairs_list
        }
        replayed_memory_ids = {
            result.intervention.target_memory_ids[0]
            for result in investigation.replay_results
            if result.intervention.target_memory_ids
        }
        pair_results: list[PairAnalysisResult] = []
        for pair in deterministic_pairs:
            semantic_pair = semantic_pairs[(pair.memory_a_id, pair.memory_b_id)]
            pair_results.append(
                PairAnalysisResult(
                    memory_a_id=pair.memory_a_id,
                    memory_b_id=pair.memory_b_id,
                    deterministic_relationship=pair,
                    semantic_relationship=semantic_pair,
                    relationships_agree=pair.relationship == semantic_pair.relationship,
                    replay_evidence_exists_for_either=(
                        pair.memory_a_id in replayed_memory_ids
                        or pair.memory_b_id in replayed_memory_ids
                    ),
                    pairwise_replay_performed=False,
                )
            )

        artifact = ContradictionAnalysisArtifact(
            metadata=self._build_metadata(
                investigation=investigation,
                response_model=semantic_result.response_model,
                prompt_version=self.prompt_settings.contradiction_prompt_version,
                prompt_hash=semantic_result.prompt_hash,
                api_usage=semantic_result.usage,
            ),
            pair_results=pair_results,
            summary=self._build_contradiction_summary(investigation_id, pair_results),
        )
        self._write_json(
            self._investigation_dir(investigation_id) / "contradictions.json",
            artifact.model_dump(mode="json"),
        )
        self._write_markdown(
            self._investigation_dir(investigation_id) / "contradictions.md",
            self._render_contradictions_markdown(artifact),
        )
        return artifact

    def compare_suspicion_replay(self, investigation_id: str) -> SuspicionRankingArtifact:
        return self.rank_memories(investigation_id)

    def show_evidence(self, investigation_id: str) -> dict[str, object]:
        ranking = self.rank_memories(investigation_id)
        contradictions = self.analyze_contradictions(investigation_id)
        return {
            "investigation_id": investigation_id,
            "suspicion_ranking": ranking.model_dump(mode="json"),
            "contradictions": contradictions.model_dump(mode="json"),
        }

    def export_analysis(self, investigation_id: str) -> dict[str, str]:
        self.rank_memories(investigation_id)
        self.analyze_contradictions(investigation_id)
        investigation_dir = self._investigation_dir(investigation_id)
        return {
            "suspicion_ranking_json": str(investigation_dir / "suspicion-ranking.json"),
            "suspicion_ranking_md": str(investigation_dir / "suspicion-ranking.md"),
            "contradictions_json": str(investigation_dir / "contradictions.json"),
            "contradictions_md": str(investigation_dir / "contradictions.md"),
        }

    def _build_metadata(
        self,
        *,
        investigation: Investigation,
        response_model: str,
        prompt_version: str,
        prompt_hash: str,
        api_usage: dict[str, int],
    ) -> AnalysisArtifactMetadata:
        return AnalysisArtifactMetadata(
            investigation_id=investigation.investigation_id,
            parent_trace_id=investigation.parent_trace_id,
            scenario_id=investigation.scenario_id,
            domain=investigation.domain,
            model=self.settings.model,
            response_model=response_model,
            semantic_analysis_prompt_version=prompt_version,
            semantic_analysis_prompt_hash=prompt_hash,
            memory_snapshot_hash=self._snapshot_hash(investigation),
            deterministic_score_configuration=self.scoring_config.documented_weights(),
            created_at=datetime.now(timezone.utc),
            api_usage=api_usage,
            git_commit_hash=self._git_commit_hash(),
        )

    def _build_ranking_summary(
        self,
        ranked_memories: list[MemoryPriorityResult],
        pair_observations: list[DeterministicPairObservation],
    ) -> InvestigationSummary:
        top_ranked = [memory.memory_id for memory in ranked_memories[:3]]
        deterministic_concerns = [
            f"{memory.memory_id}: {', '.join(memory.deterministic_reasons)}"
            for memory in ranked_memories
            if memory.deterministic_reasons
        ]
        semantic_concerns = [
            f"{memory.memory_id}: {memory.semantic_reason}" for memory in ranked_memories
        ]
        contradictions = [
            f"{pair.memory_a_id}/{pair.memory_b_id}: {pair.concise_reason}"
            for pair in pair_observations
            if pair.relationship.value in {"contradicts", "supersedes", "temporal_overlap"}
        ]
        replay_supported = [
            memory.memory_id
            for memory in ranked_memories
            if memory.comparison_classification
            == ReplayComparisonClassification.SUPPORTED_BY_REPLAY
        ]
        suspicious_without_influence = [
            memory.memory_id
            for memory in ranked_memories
            if memory.comparison_classification
            == ReplayComparisonClassification.NOT_SUPPORTED_BY_REPLAY
            and memory.prioritization_score >= 0.5
        ]
        return InvestigationSummary(
            top_ranked_memories=top_ranked,
            deterministic_concerns=deterministic_concerns,
            semantic_concerns=semantic_concerns,
            contradictions_detected=contradictions,
            replay_supported_memories=replay_supported,
            suspicious_memories_with_no_observed_influence=suspicious_without_influence,
            pairwise_testing_recommended=bool(suspicious_without_influence),
            no_memory_or_prompt_only_testing_recommended=not replay_supported,
            human_review_recommended=any(
                memory.semantic_hypothesis.requires_human_review for memory in ranked_memories
            ),
        )

    def _build_contradiction_summary(
        self,
        investigation_id: str,
        pair_results: list[PairAnalysisResult],
    ) -> InvestigationSummary:
        ranking = self._load_ranking_if_present(investigation_id)
        return InvestigationSummary(
            top_ranked_memories=ranking.summary.top_ranked_memories if ranking else [],
            deterministic_concerns=ranking.summary.deterministic_concerns if ranking else [],
            semantic_concerns=ranking.summary.semantic_concerns if ranking else [],
            contradictions_detected=[
                (
                    f"{pair.memory_a_id}/{pair.memory_b_id}: "
                    f"{pair.deterministic_relationship.relationship.value} vs "
                    f"{pair.semantic_relationship.relationship.value}"
                )
                for pair in pair_results
                if pair.deterministic_relationship.relationship.value
                in {"contradicts", "supersedes", "temporal_overlap"}
                or pair.semantic_relationship.relationship.value in {"contradicts", "supersedes"}
            ],
            replay_supported_memories=ranking.summary.replay_supported_memories if ranking else [],
            suspicious_memories_with_no_observed_influence=(
                ranking.summary.suspicious_memories_with_no_observed_influence if ranking else []
            ),
            pairwise_testing_recommended=any(not pair.relationships_agree for pair in pair_results),
            no_memory_or_prompt_only_testing_recommended=not any(
                pair.relationships_agree for pair in pair_results
            ),
            human_review_recommended=any(
                pair.semantic_relationship.requires_human_review for pair in pair_results
            ),
        )

    def _load_ranking_if_present(
        self,
        investigation_id: str,
    ) -> SuspicionRankingArtifact | None:
        path = self._investigation_dir(investigation_id) / "suspicion-ranking.json"
        if not path.exists():
            return None
        return SuspicionRankingArtifact.model_validate_json(path.read_text(encoding="utf-8"))

    def _render_ranking_markdown(self, artifact: SuspicionRankingArtifact) -> str:
        lines = [
            "# Suspicion Ranking",
            "",
            f"- Investigation ID: `{artifact.metadata.investigation_id}`",
            f"- Scenario: `{artifact.metadata.scenario_id}`",
            f"- Model: `{artifact.metadata.model}`",
            "",
            "## Ranked Memories",
            "",
        ]
        for memory in artifact.memories:
            lines.extend(
                [
                    f"- `{memory.memory_id}`",
                    (
                        f"  deterministic={memory.deterministic_score:.3f}, "
                        f"semantic={memory.semantic_score:.3f}, "
                        f"priority={memory.prioritization_score:.3f}, "
                        f"replay={memory.replay_supported_evidence.evidence_status_label.value}"
                    ),
                    f"  semantic reason: {memory.semantic_reason}",
                ]
            )
        if artifact.metadata.scenario_id == "exp_09":
            lines.extend(
                [
                    "",
                    "## Investigation Note",
                    "",
                    "- All individual replay influence values remain `0.0`.",
                    "- Suspicion analysis does not override the replay result.",
                    "- Pairwise or whole-snapshot testing may still be needed.",
                    "- Prompt or policy interpretation remains a possible cause.",
                ]
            )
        return "\n".join(lines) + "\n"

    def _render_contradictions_markdown(
        self,
        artifact: ContradictionAnalysisArtifact,
    ) -> str:
        lines = [
            "# Contradiction Analysis",
            "",
            f"- Investigation ID: `{artifact.metadata.investigation_id}`",
            f"- Scenario: `{artifact.metadata.scenario_id}`",
            "",
            "## Pairs",
            "",
        ]
        for pair in artifact.pair_results:
            lines.append(
                (
                    f"- `{pair.memory_a_id}` / `{pair.memory_b_id}`: "
                    f"metadata={pair.deterministic_relationship.relationship.value}, "
                    f"semantic={pair.semantic_relationship.relationship.value}, "
                    f"agree={pair.relationships_agree}"
                )
            )
        return "\n".join(lines) + "\n"

    def _snapshot_hash(self, investigation: Investigation) -> str:
        hashed = hashlib.sha256()
        payload = [
            memory.model_dump(mode="json") for memory in investigation.original_memory_snapshot
        ]
        hashed.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return hashed.hexdigest()

    def _git_commit_hash(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3],
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    def _get_trace(self, trace_id: str) -> ExecutionTrace:
        trace = self.repository.get_trace(trace_id)
        if trace is None:
            raise ValueError(f"unknown trace: {trace_id}")
        return trace

    def _investigation_dir(self, investigation_id: str) -> Path:
        return self.artifacts_dir / "investigations" / investigation_id

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_markdown(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
