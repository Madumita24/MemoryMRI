from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from memory_mri.analysis.engine import InvestigationAnalysisEngine
from memory_mri.analysis.models import ContradictionAnalysisArtifact, SuspicionRankingArtifact
from memory_mri.config import OpenAISettings, SemanticAnalysisSettings
from memory_mri.db.session import create_sqlite_session
from memory_mri.engine.counterfactual_replay import CounterfactualReplayEngine
from memory_mri.prompts.loader import load_analysis_prompt
from memory_mri.repositories.store import BenchmarkRepository
from memory_mri.schemas import (
    AgentInputMemory,
    DecisionSupportAudit,
    ExecutionTrace,
    Investigation,
    MemoryControlsArtifact,
    MemoryDependenceClassification,
    PairwiseReplayArtifact,
    ProposalContradictionEvidence,
    ProposalEvidenceReference,
    ProposalReplayEvidence,
    ProposalSuspicionEvidence,
    RepairProposal,
    RepairStatus,
    RepairType,
    ReplayResult,
    SupportValidityResult,
)

MEMORY_EDITING_REPAIR_TYPES = {
    RepairType.INVALIDATE_MEMORY,
    RepairType.ADD_EXPIRATION_DATE,
    RepairType.MARK_SUPERSEDED,
    RepairType.CORRECT_ENTITY_ASSOCIATION,
    RepairType.MERGE_CONTRADICTORY_MEMORIES,
    RepairType.LOWER_RETRIEVAL_PRIORITY,
    RepairType.REPLACE_WITH_CORRECTED_FACT,
}

CAUTIOUS_REPAIR_TYPES = {
    RepairType.ADD_CONTEXT_CONSTRAINT,
    RepairType.ADD_PRECEDENCE_METADATA,
    RepairType.REQUIRE_HUMAN_CONFIRMATION,
    RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
    RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
}


class ParsedResponseLike(Protocol):
    id: str
    model: str
    usage: Any
    output_text: str


class ResponsesAPI(Protocol):
    def create(self, **kwargs: Any) -> ParsedResponseLike: ...


class OpenAIClientLike(Protocol):
    responses: ResponsesAPI


class RepairProposalFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    attempts: int


class RepairProposalError(Exception):
    def __init__(self, failure: RepairProposalFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


class RepairProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repair_type: RepairType
    target_memory_ids: list[str] = Field(default_factory=list)
    proposed_after_state: list["RepairStateUpdate"]
    expected_affected_scenarios: list[str] = Field(default_factory=list)
    expected_behavior_change: str = Field(min_length=1, max_length=400)
    risks: list[str] = Field(min_length=1)
    rollback_plan: str = Field(min_length=1, max_length=400)
    concise_explanation: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: bool

    @field_validator("target_memory_ids", "expected_affected_scenarios")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value


class RepairStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    new_value: str = Field(min_length=1)


@dataclass(frozen=True)
class GateDecision:
    outcome_type: RepairType | None
    allowed_repair_types: list[RepairType]
    support_validity: SupportValidityResult
    explanation: str
    strongest_replay: ReplayResult | None
    strongest_control: DecisionSupportAudit | None
    evidence_gate_passed: bool


class RepairProposalEngine:
    def __init__(
        self,
        *,
        database_url: str,
        data_dir: Path,
        artifacts_dir: Path,
        settings: OpenAISettings | None = None,
        prompt_settings: SemanticAnalysisSettings | None = None,
        client: OpenAIClientLike | None = None,
        analysis_engine: InvestigationAnalysisEngine | None = None,
        replay_engine: CounterfactualReplayEngine | None = None,
    ) -> None:
        self.session = create_sqlite_session(database_url)
        self.repository = BenchmarkRepository(self.session)
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir
        self.settings = settings or OpenAISettings.from_env()
        self.prompt_settings = prompt_settings or SemanticAnalysisSettings.from_env()
        self._client: OpenAIClientLike | None = client
        self.analysis_engine = analysis_engine or InvestigationAnalysisEngine(
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            settings=self.settings,
            prompt_settings=self.prompt_settings,
        )
        self.replay_engine = replay_engine or CounterfactualReplayEngine(
            database_url=database_url,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
        )

    def generate_proposal(self, investigation_id: str) -> RepairProposal:
        investigation = self.replay_engine.load_investigation(investigation_id)
        parent_trace = self._get_trace(investigation.parent_trace_id)
        suspicion = self._load_or_build_suspicion(investigation_id)
        contradictions = self._load_or_build_contradictions(investigation_id)
        controls = self._load_or_build_controls(investigation_id)
        pairwise = self._load_pairwise_if_present(investigation_id)
        gate = self._evaluate_gate(investigation, controls)
        evidence_reference = self._build_evidence_reference(
            investigation=investigation,
            prompt_hash=investigation.prompt_content_hash,
            contradiction_artifact_present=contradictions is not None,
        )
        replay_evidence = self._build_replay_evidence(investigation, controls, evidence_reference)
        suspicion_evidence = self._build_suspicion_evidence(suspicion, evidence_reference)
        contradiction_evidence = self._build_contradiction_evidence(
            contradictions,
            evidence_reference,
        )
        before_state = self._before_state(
            investigation=investigation,
            parent_trace=parent_trace,
            controls=controls,
            pairwise=pairwise,
            gate=gate,
        )
        if gate.outcome_type is not None:
            proposal = self._build_non_gpt_proposal(
                investigation=investigation,
                repair_type=gate.outcome_type,
                replay_evidence=replay_evidence,
                suspicion_evidence=suspicion_evidence,
                contradiction_evidence=contradiction_evidence,
                support_validity=gate.support_validity,
                before_state=before_state,
                evidence_reference=evidence_reference,
                explanation=gate.explanation,
            )
        else:
            draft = self._generate_gpt_draft(
                investigation=investigation,
                parent_trace=parent_trace,
                replay_evidence=replay_evidence,
                suspicion_evidence=suspicion_evidence,
                contradiction_evidence=contradiction_evidence,
                support_validity=gate.support_validity,
                allowed_repair_types=gate.allowed_repair_types,
                memory_dependence_classification=controls.memory_dependence_classification,
            )
            self._validate_draft(
                investigation=investigation,
                draft=draft,
                allowed_repair_types=gate.allowed_repair_types,
                strongest_replay=gate.strongest_replay,
            )
            proposal = RepairProposal(
                proposal_id=f"proposal_{uuid4().hex}",
                investigation_id=investigation.investigation_id,
                scenario_id=investigation.scenario_id,
                domain=investigation.domain,
                repair_type=draft.repair_type,
                target_memory_ids=draft.target_memory_ids,
                before_state=before_state,
                proposed_after_state={
                    update.field_name: update.new_value for update in draft.proposed_after_state
                },
                replay_evidence=replay_evidence,
                suspicion_evidence=suspicion_evidence,
                contradiction_evidence=contradiction_evidence,
                support_validity_result=gate.support_validity,
                expected_affected_scenarios=draft.expected_affected_scenarios,
                expected_behavior_change=draft.expected_behavior_change,
                risks=draft.risks,
                rollback_plan=draft.rollback_plan,
                concise_explanation=draft.concise_explanation,
                confidence=draft.confidence,
                requires_human_approval=draft.requires_human_approval,
                proposal_status=RepairStatus.PROPOSED,
                model=self.settings.model,
                prompt_version=self.prompt_settings.repair_prompt_version,
                created_at=datetime.now(timezone.utc),
                evidence_references=evidence_reference,
            )
        self._persist_proposal(proposal)
        return proposal

    def list_proposals(self, investigation_id: str) -> list[RepairProposal]:
        return self.repository.list_repair_proposals_for_investigation(investigation_id)

    def get_proposal(self, proposal_id: str) -> RepairProposal:
        proposal = self.repository.get_repair_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"unknown proposal: {proposal_id}")
        return proposal

    def export_proposal(self, proposal_id: str) -> dict[str, str]:
        proposal = self.get_proposal(proposal_id)
        proposal_dir = self._proposal_dir(proposal.investigation_id)
        json_path = proposal_dir / f"{proposal.proposal_id}.json"
        md_path = proposal_dir / f"{proposal.proposal_id}.md"
        return {
            "proposal_json": str(json_path),
            "proposal_markdown": str(md_path),
        }

    def explain_no_repair(self, proposal_id: str) -> str:
        proposal = self.get_proposal(proposal_id)
        if proposal.repair_type not in {
            RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
            RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
        }:
            raise ValueError("proposal is not a no-repair or escalation outcome")
        return proposal.concise_explanation

    def _load_or_build_suspicion(self, investigation_id: str) -> SuspicionRankingArtifact:
        path = self._investigation_dir(investigation_id) / "suspicion-ranking.json"
        if path.exists():
            return SuspicionRankingArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        return self.analysis_engine.rank_memories(investigation_id)

    def _load_or_build_contradictions(
        self,
        investigation_id: str,
    ) -> ContradictionAnalysisArtifact:
        path = self._investigation_dir(investigation_id) / "contradictions.json"
        if path.exists():
            return ContradictionAnalysisArtifact.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return self.analysis_engine.analyze_contradictions(investigation_id)

    def _load_or_build_controls(self, investigation_id: str) -> MemoryControlsArtifact:
        path = self._investigation_dir(investigation_id) / "memory-controls.json"
        if path.exists():
            return MemoryControlsArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        return self.replay_engine.export_memory_controls(investigation_id)

    def _load_pairwise_if_present(self, investigation_id: str) -> PairwiseReplayArtifact | None:
        path = self._investigation_dir(investigation_id) / "pairwise-replay.json"
        if not path.exists():
            return None
        return PairwiseReplayArtifact.model_validate_json(path.read_text(encoding="utf-8"))

    def _evaluate_gate(
        self,
        investigation: Investigation,
        controls: MemoryControlsArtifact,
    ) -> GateDecision:
        strongest_replay = self._strongest_behavior_change(investigation.replay_results)
        no_memory_preserves_wrong_action = (
            controls.no_memory_control.control_action_distribution
            == controls.no_memory_control.original_action_distribution
        )
        memory_independent = (
            controls.memory_dependence_classification
            == MemoryDependenceClassification.LIKELY_MEMORY_INDEPENDENT
        )
        if strongest_replay is None or memory_independent:
            explanation = (
                "Replay evidence does not justify a memory edit. "
                "The failure appears memory-independent or remains unchanged without memory."
            )
            return GateDecision(
                outcome_type=RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
                allowed_repair_types=[RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW],
                support_validity=SupportValidityResult(
                    decision_still_supported=False,
                    outcome_correct=False,
                    requires_human_review=True,
                    support_explanation=explanation,
                ),
                explanation=explanation,
                strongest_replay=strongest_replay,
                strongest_control=controls.no_memory_control.support_validity,
                evidence_gate_passed=False,
            )

        if not self._supports_expected_action(controls):
            explanation = (
                "Replay showed a behavior change, but the changed action is not fully supported "
                "by the remaining evidence. Only cautious, human-reviewed "
                "recommendations are allowed."
            )
            return GateDecision(
                outcome_type=None,
                allowed_repair_types=sorted(CAUTIOUS_REPAIR_TYPES, key=lambda item: item.value),
                support_validity=SupportValidityResult(
                    decision_still_supported=False,
                    outcome_correct=True,
                    requires_human_review=True,
                    support_explanation=(
                        f"{self._support_explanation_for_result(strongest_replay)} "
                        f"No-memory control preserved the original wrong action: "
                        f"{no_memory_preserves_wrong_action}."
                    ),
                ),
                explanation=explanation,
                strongest_replay=strongest_replay,
                strongest_control=None,
                evidence_gate_passed=True,
            )

        return GateDecision(
            outcome_type=None,
            allowed_repair_types=sorted(
                MEMORY_EDITING_REPAIR_TYPES | CAUTIOUS_REPAIR_TYPES,
                key=lambda item: item.value,
            ),
            support_validity=SupportValidityResult(
                decision_still_supported=True,
                outcome_correct=True,
                requires_human_review=True,
                support_explanation=self._support_explanation_for_result(strongest_replay),
            ),
            explanation="Evidence gates passed for a repair proposal.",
            strongest_replay=strongest_replay,
            strongest_control=None,
            evidence_gate_passed=True,
        )

    def _strongest_behavior_change(self, replay_results: list[ReplayResult]) -> ReplayResult | None:
        changed = [
            result
            for result in replay_results
            if result.original_action_distribution != result.intervention_action_distribution
        ]
        if not changed:
            return None
        return max(
            changed,
            key=lambda result: (
                abs(result.influence_delta),
                result.success_rate,
                ",".join(result.intervention.target_memory_ids),
            ),
        )

    def _supports_expected_action(self, controls: MemoryControlsArtifact) -> bool:
        return any(
            result.control_successful_runs > 0 and result.support_validity.decision_still_supported
            for result in controls.isolation_controls
        )

    def _support_explanation_for_result(self, replay_result: ReplayResult) -> str:
        target = ", ".join(replay_result.intervention.target_memory_ids)
        return (
            f"Intervention {replay_result.intervention.intervention_type} on {target} changed the "
            f"action distribution to {replay_result.intervention_action_distribution}, but support "
            "must be checked separately before treating it as a valid repair."
        )

    def _build_evidence_reference(
        self,
        *,
        investigation: Investigation,
        prompt_hash: str | None,
        contradiction_artifact_present: bool,
    ) -> ProposalEvidenceReference:
        replay_artifact_ids = [
            name
            for name in (
                "investigation.json",
                "memory-controls.json",
                "pairwise-replay.json",
                "suspicion-ranking.json",
            )
            if (self._investigation_dir(investigation.investigation_id) / name).exists()
        ]
        return ProposalEvidenceReference(
            parent_trace_id=investigation.parent_trace_id,
            replay_artifact_ids=replay_artifact_ids,
            contradiction_artifact_ids=["contradictions.json"]
            if contradiction_artifact_present
            else [],
            memory_snapshot_hash=self._snapshot_hash(investigation.original_memory_snapshot),
            git_commit_hash=self._git_commit_hash(),
            prompt_hash=prompt_hash,
        )

    def _build_replay_evidence(
        self,
        investigation: Investigation,
        controls: MemoryControlsArtifact,
        evidence_reference: ProposalEvidenceReference,
    ) -> ProposalReplayEvidence:
        strongest = self._strongest_behavior_change(investigation.replay_results)
        return ProposalReplayEvidence(
            replay_evidence_exists=bool(investigation.replay_results),
            behavior_change_observed=strongest is not None,
            memory_dependent_failure=(
                controls.memory_dependence_classification
                != MemoryDependenceClassification.LIKELY_MEMORY_INDEPENDENT
            ),
            no_memory_control_preserved_wrong_action=(
                controls.no_memory_control.control_action_distribution
                == controls.no_memory_control.original_action_distribution
            ),
            strongest_intervention_type=(
                strongest.intervention.intervention_type.value if strongest is not None else None
            ),
            strongest_target_memory_ids=(
                strongest.intervention.target_memory_ids if strongest is not None else []
            ),
            strongest_influence_delta=(
                strongest.influence_delta if strongest is not None else None
            ),
            strongest_action_distribution=(
                strongest.intervention_action_distribution if strongest is not None else {}
            ),
            support_explanation=(
                self._support_explanation_for_result(strongest)
                if strongest is not None
                else "No behavior-changing replay evidence was observed."
            ),
            evidence_references=evidence_reference,
        )

    def _build_suspicion_evidence(
        self,
        suspicion: SuspicionRankingArtifact,
        evidence_reference: ProposalEvidenceReference,
    ) -> ProposalSuspicionEvidence:
        return ProposalSuspicionEvidence(
            top_ranked_memory_ids=suspicion.summary.top_ranked_memories,
            replay_supported_memory_ids=suspicion.summary.replay_supported_memories,
            suspicious_without_observed_influence=(
                suspicion.summary.suspicious_memories_with_no_observed_influence
            ),
            semantic_hypotheses=[
                f"{memory.memory_id}: {memory.semantic_reason}" for memory in suspicion.memories[:3]
            ],
            evidence_references=evidence_reference,
        )

    def _build_contradiction_evidence(
        self,
        contradictions: ContradictionAnalysisArtifact,
        evidence_reference: ProposalEvidenceReference,
    ) -> ProposalContradictionEvidence:
        contradiction_pairs = [
            f"{pair.memory_a_id}/{pair.memory_b_id}"
            for pair in contradictions.pair_results
            if pair.deterministic_relationship.relationship.value in {"contradicts", "supersedes"}
            or pair.semantic_relationship.relationship.value in {"contradicts", "supersedes"}
        ]
        target_memory_ids = sorted(
            {
                memory_id
                for pair in contradictions.pair_results
                if f"{pair.memory_a_id}/{pair.memory_b_id}" in contradiction_pairs
                for memory_id in (pair.memory_a_id, pair.memory_b_id)
            }
        )
        return ProposalContradictionEvidence(
            contradiction_pairs=contradiction_pairs,
            contradictory_target_memory_ids=target_memory_ids,
            semantic_findings=[
                (
                    f"{pair.memory_a_id}/{pair.memory_b_id}: "
                    f"{pair.semantic_relationship.concise_explanation}"
                )
                for pair in contradictions.pair_results[:3]
            ],
            evidence_references=evidence_reference,
        )

    def _before_state(
        self,
        *,
        investigation: Investigation,
        parent_trace: ExecutionTrace,
        controls: MemoryControlsArtifact,
        pairwise: PairwiseReplayArtifact | None,
        gate: GateDecision,
    ) -> dict[str, Any]:
        return {
            "original_selected_action": parent_trace.selected_action,
            "expected_action": investigation.expected_action,
            "memory_ids": [memory.memory_id for memory in investigation.original_memory_snapshot],
            "memory_dependence_classification": controls.memory_dependence_classification.value,
            "pairwise_memory_dependence_classification": (
                pairwise.memory_dependence_classification.value if pairwise is not None else None
            ),
            "evidence_gate_passed": gate.evidence_gate_passed,
        }

    def _build_non_gpt_proposal(
        self,
        *,
        investigation: Investigation,
        repair_type: RepairType,
        replay_evidence: ProposalReplayEvidence,
        suspicion_evidence: ProposalSuspicionEvidence,
        contradiction_evidence: ProposalContradictionEvidence,
        support_validity: SupportValidityResult,
        before_state: dict[str, Any],
        evidence_reference: ProposalEvidenceReference,
        explanation: str,
    ) -> RepairProposal:
        if repair_type == RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW:
            risks = [
                "Prompt-level problem mistaken for a memory problem.",
                "Broader behavior changes could be hidden outside the memory layer.",
                (
                    "Editing memories here could erase valid historical information without "
                    "fixing the failure."
                ),
            ]
            behavior = (
                "Escalate review of prompt or policy interpretation instead of editing memory."
            )
        else:
            risks = [
                "Semantic suspicion alone does not justify a repair.",
                "A premature memory edit could remove valid information.",
                (
                    "Neighboring scenarios could regress if the memory system is changed "
                    "without stronger evidence."
                ),
            ]
            behavior = (
                "Preserve the current memory snapshot and collect more evidence before "
                "proposing edits."
            )
        return RepairProposal(
            proposal_id=f"proposal_{uuid4().hex}",
            investigation_id=investigation.investigation_id,
            scenario_id=investigation.scenario_id,
            domain=investigation.domain,
            repair_type=repair_type,
            target_memory_ids=[],
            before_state=before_state,
            proposed_after_state={"action": "none"},
            replay_evidence=replay_evidence,
            suspicion_evidence=suspicion_evidence,
            contradiction_evidence=contradiction_evidence,
            support_validity_result=support_validity,
            expected_affected_scenarios=[],
            expected_behavior_change=behavior,
            risks=risks,
            rollback_plan=(
                "No memory change is applied. Re-run investigation after prompt or policy review."
            ),
            concise_explanation=explanation,
            confidence=0.95 if repair_type == RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW else 0.9,
            requires_human_approval=True,
            proposal_status=RepairStatus.PROPOSED,
            model="deterministic-evidence-gate",
            prompt_version=self.prompt_settings.repair_prompt_version,
            created_at=datetime.now(timezone.utc),
            evidence_references=evidence_reference,
        )

    def _generate_gpt_draft(
        self,
        *,
        investigation: Investigation,
        parent_trace: ExecutionTrace,
        replay_evidence: ProposalReplayEvidence,
        suspicion_evidence: ProposalSuspicionEvidence,
        contradiction_evidence: ProposalContradictionEvidence,
        support_validity: SupportValidityResult,
        allowed_repair_types: list[RepairType],
        memory_dependence_classification: MemoryDependenceClassification,
    ) -> RepairProposalDraft:
        if not self.settings.api_key:
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_api_key",
                    message="OPENAI_API_KEY is required for repair proposal generation",
                    retryable=False,
                    attempts=0,
                )
            )
        prompt = load_analysis_prompt(
            "memory_repair_proposal",
            self.prompt_settings.repair_prompt_version,
        )
        payload = {
            "scenario_id": investigation.scenario_id,
            "domain": investigation.domain.value,
            "agent_visible_memory_snapshot": [
                memory.model_dump(mode="json") for memory in investigation.original_memory_snapshot
            ],
            "original_action": parent_trace.selected_action,
            "expected_action": investigation.expected_action,
            "replay_evidence": replay_evidence.model_dump(mode="json"),
            "suspicion_evidence": suspicion_evidence.model_dump(mode="json"),
            "contradiction_evidence": contradiction_evidence.model_dump(mode="json"),
            "support_validity_result": support_validity.model_dump(mode="json"),
            "memory_dependence_classification": memory_dependence_classification.value,
            "allowed_repair_types": [repair_type.value for repair_type in allowed_repair_types],
        }
        attempts = 0
        while attempts <= self.settings.max_retries:
            attempts += 1
            try:
                response = self._get_client().responses.create(
                    model=self.settings.model,
                    instructions=prompt,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": json.dumps(payload, indent=2)}
                            ],
                        }
                    ],
                    reasoning=self._build_reasoning(),
                    text=self._build_text_config(RepairProposalDraft),
                    timeout=self.settings.timeout_seconds,
                )
                return RepairProposalDraft.model_validate_json(response.output_text)
            except ValidationError as exc:
                raise RepairProposalError(
                    RepairProposalFailure(
                        code="invalid_model_output",
                        message=f"Repair proposal output failed validation: {exc}",
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc
            except (
                APITimeoutError,
                APIConnectionError,
                RateLimitError,
                InternalServerError,
                ConflictError,
            ) as exc:
                if attempts > self.settings.max_retries:
                    raise RepairProposalError(
                        RepairProposalFailure(
                            code="transient_openai_error",
                            message=str(exc),
                            retryable=True,
                            attempts=attempts,
                        )
                    ) from exc
            except (AuthenticationError, BadRequestError) as exc:
                raise RepairProposalError(
                    RepairProposalFailure(
                        code="permanent_openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc
            except APIStatusError as exc:
                retryable = exc.status_code >= 500
                if retryable and attempts <= self.settings.max_retries:
                    continue
                raise RepairProposalError(
                    RepairProposalFailure(
                        code="openai_status_error",
                        message=str(exc),
                        retryable=retryable,
                        attempts=attempts,
                    )
                ) from exc
            except OpenAIError as exc:
                raise RepairProposalError(
                    RepairProposalFailure(
                        code="openai_error",
                        message=str(exc),
                        retryable=False,
                        attempts=attempts,
                    )
                ) from exc
        raise RepairProposalError(
            RepairProposalFailure(
                code="unknown_repair_failure",
                message="Repair proposal generation failed without a captured exception",
                retryable=False,
                attempts=attempts,
            )
        )

    def _validate_draft(
        self,
        *,
        investigation: Investigation,
        draft: RepairProposalDraft,
        allowed_repair_types: list[RepairType],
        strongest_replay: ReplayResult | None,
    ) -> None:
        if draft.repair_type not in allowed_repair_types:
            raise RepairProposalError(
                RepairProposalFailure(
                    code="invalid_repair_type",
                    message=f"Repair type is not allowed by the evidence gate: {draft.repair_type}",
                    retryable=False,
                    attempts=1,
                )
            )
        known_memory_ids = {memory.memory_id for memory in investigation.original_memory_snapshot}
        unknown_target_ids = [
            memory_id for memory_id in draft.target_memory_ids if memory_id not in known_memory_ids
        ]
        if unknown_target_ids:
            raise RepairProposalError(
                RepairProposalFailure(
                    code="invalid_target_memory_ids",
                    message=f"Unknown target memory IDs: {unknown_target_ids}",
                    retryable=False,
                    attempts=1,
                )
            )
        if (
            draft.repair_type in MEMORY_EDITING_REPAIR_TYPES
            and strongest_replay is not None
            and not set(draft.target_memory_ids).intersection(
                strongest_replay.intervention.target_memory_ids
            )
        ):
            raise RepairProposalError(
                RepairProposalFailure(
                    code="unrelated_memory_edit",
                    message=(
                        "Memory-editing proposal does not target the observed intervention memory."
                    ),
                    retryable=False,
                    attempts=1,
                )
            )

    def _persist_proposal(self, proposal: RepairProposal) -> None:
        self.repository.save_repair_proposal(proposal)
        self.session.commit()
        proposal_dir = self._proposal_dir(proposal.investigation_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)
        (proposal_dir / f"{proposal.proposal_id}.json").write_text(
            proposal.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (proposal_dir / f"{proposal.proposal_id}.md").write_text(
            self._render_proposal_markdown(proposal),
            encoding="utf-8",
        )

    def _render_proposal_markdown(self, proposal: RepairProposal) -> str:
        lines = [
            "# Repair Proposal",
            "",
            f"- Proposal ID: `{proposal.proposal_id}`",
            f"- Investigation ID: `{proposal.investigation_id}`",
            f"- Scenario ID: `{proposal.scenario_id}`",
            f"- Repair type: `{proposal.repair_type.value}`",
            f"- Human approval required: `{proposal.requires_human_approval}`",
            "",
            "## Explanation",
            "",
            proposal.concise_explanation,
            "",
            "## Risks",
            "",
        ]
        lines.extend([f"- {risk}" for risk in proposal.risks])
        lines.extend(
            [
                "",
                "## Expected Change",
                "",
                proposal.expected_behavior_change,
                "",
                "## Rollback",
                "",
                proposal.rollback_plan,
                "",
            ]
        )
        return "\n".join(lines)

    def _build_text_config(self, response_model: type[BaseModel]) -> dict[str, object]:
        config: dict[str, object] = {
            "format": {
                "type": "json_schema",
                "name": response_model.__name__,
                "strict": True,
                "schema": to_strict_json_schema(response_model),
            }
        }
        if self.settings.verbosity is not None:
            config["verbosity"] = self.settings.verbosity
        return config

    def _build_reasoning(self) -> dict[str, str] | None:
        if self.settings.reasoning_effort is None:
            return None
        return {"effort": self.settings.reasoning_effort}

    def _get_client(self) -> OpenAIClientLike:
        if self._client is None:
            self._client = cast(
                OpenAIClientLike,
                OpenAI(
                    api_key=self.settings.api_key,
                    timeout=self.settings.timeout_seconds,
                    max_retries=0,
                ),
            )
        return self._client

    def _get_trace(self, trace_id: str) -> ExecutionTrace:
        trace = self.repository.get_trace(trace_id)
        if trace is None:
            raise ValueError(f"unknown trace: {trace_id}")
        return trace

    def _investigation_dir(self, investigation_id: str) -> Path:
        return self.artifacts_dir / "investigations" / investigation_id

    def _proposal_dir(self, investigation_id: str) -> Path:
        return self._investigation_dir(investigation_id) / "repair-proposals"

    def _snapshot_hash(self, memories: list[AgentInputMemory]) -> str:
        payload = [memory.model_dump(mode="json") for memory in memories]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _git_commit_hash(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3],
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
