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
    ApprovalRecord,
    AuditEventType,
    AuditLogEntry,
    DecisionSupportAudit,
    ExecutionTrace,
    Investigation,
    MemoryControlsArtifact,
    MemoryDependenceClassification,
    MemoryDiff,
    MemoryDiffChangeType,
    MemoryDiffFrontendSection,
    MemoryDiffMode,
    MemoryDiffRiskLevel,
    MemoryFieldChange,
    MemoryStatus,
    MemoryStoreVersion,
    MemoryVersionStatus,
    PairwiseReplayArtifact,
    ProposalContradictionEvidence,
    ProposalEvidenceReference,
    ProposalReplayEvidence,
    ProposalSuspicionEvidence,
    RejectionRecord,
    RepairProposal,
    RepairStatus,
    RepairType,
    ReplayResult,
    SupportValidityResult,
)

ABSENT = {"__memory_mri_absent__": True}
REDACTED = "[REDACTED]"
SECRET_FIELD_TOKENS = ("secret", "token", "password", "api_key", "authorization", "auth")

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

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        approval_reason: str,
        evidence_reviewed: list[str] | None = None,
        acknowledged_risks: list[str] | None = None,
        approver_id: str = "local_user",
        notes: str | None = None,
    ) -> RepairProposal:
        proposal = self.get_proposal(proposal_id)
        self._transition_or_error(proposal, RepairStatus.APPROVED, actor=approver_id)
        approval_record = ApprovalRecord(
            proposal_id=proposal.proposal_id,
            approver_id=approver_id,
            approval_reason=approval_reason,
            approved_at=datetime.now(timezone.utc),
            evidence_reviewed=evidence_reviewed or self._default_evidence_reviewed(proposal),
            acknowledged_risks=acknowledged_risks or list(proposal.risks),
            notes=notes,
        )
        updated = proposal.model_copy(
            update={
                "proposal_status": RepairStatus.APPROVED,
                "approval_record": approval_record,
            },
            deep=True,
        )
        self.repository.save_repair_proposal(updated)
        self.repository.save_approval_record(approval_record, updated.scenario_id)
        self._record_audit(
            proposal=updated,
            event_type=AuditEventType.PROPOSAL_APPROVED,
            actor=approver_id,
            status_from=proposal.proposal_status,
            status_to=updated.proposal_status,
            details={"approval_reason": approval_reason},
        )
        self.session.commit()
        self._write_proposal_artifacts(updated)
        return updated

    def reject_proposal(
        self,
        proposal_id: str,
        *,
        rejection_reason: str,
        actor_id: str = "local_user",
        notes: str | None = None,
    ) -> RepairProposal:
        proposal = self.get_proposal(proposal_id)
        self._transition_or_error(proposal, RepairStatus.REJECTED, actor=actor_id)
        rejection_record = RejectionRecord(
            proposal_id=proposal.proposal_id,
            actor_id=actor_id,
            rejection_reason=rejection_reason,
            rejected_at=datetime.now(timezone.utc),
            notes=notes,
        )
        updated = proposal.model_copy(
            update={
                "proposal_status": RepairStatus.REJECTED,
                "rejection_record": rejection_record,
            },
            deep=True,
        )
        self.repository.save_repair_proposal(updated)
        self._record_audit(
            proposal=updated,
            event_type=AuditEventType.PROPOSAL_REJECTED,
            actor=actor_id,
            status_from=proposal.proposal_status,
            status_to=updated.proposal_status,
            details={"rejection_reason": rejection_reason},
        )
        self.session.commit()
        self._write_proposal_artifacts(updated)
        return updated

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        actor_id: str = "local_user",
    ) -> MemoryStoreVersion:
        proposal = self.get_proposal(proposal_id)
        self._transition_or_error(proposal, RepairStatus.APPLIED, actor=actor_id)
        if proposal.repair_type in {
            RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
            RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
        }:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="This proposal type must not modify memory or create a version.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="non_applicable_repair_type",
                    message="This proposal type must not modify memory or create a version.",
                    retryable=False,
                    attempts=1,
                )
            )
        investigation = self.replay_engine.load_investigation(proposal.investigation_id)
        self._validate_apply_readiness(proposal, investigation, actor_id)
        current_version = self._get_or_create_base_version(investigation)
        if current_version.snapshot_hash != proposal.evidence_references.memory_snapshot_hash:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Proposal is stale because the current memory snapshot has changed.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="stale_snapshot_hash",
                    message="Proposal is stale because the current memory snapshot has changed.",
                    retryable=False,
                    attempts=1,
                )
            )
        updated_snapshot = self._apply_repair_to_snapshot(
            proposal=proposal,
            snapshot=current_version.memory_snapshot,
        )
        current_version.status = MemoryVersionStatus.SUPERSEDED
        self.repository.save_memory_version(current_version)
        applied_version = MemoryStoreVersion(
            version_id=f"version_{uuid4().hex}",
            parent_version_id=current_version.version_id,
            investigation_id=proposal.investigation_id,
            proposal_id=proposal.proposal_id,
            scenario_id=proposal.scenario_id,
            created_at=datetime.now(timezone.utc),
            created_by=actor_id,
            memory_snapshot=updated_snapshot,
            snapshot_hash=self._snapshot_hash(updated_snapshot),
            change_summary=self._change_summary(proposal),
            status=MemoryVersionStatus.ACTIVE,
        )
        self.repository.save_memory_version(applied_version)
        updated_proposal = proposal.model_copy(
            update={
                "proposal_status": RepairStatus.APPLIED,
                "applied_version_id": applied_version.version_id,
            },
            deep=True,
        )
        self.repository.save_repair_proposal(updated_proposal)
        self._record_audit(
            proposal=updated_proposal,
            event_type=AuditEventType.PROPOSAL_APPLIED,
            actor=actor_id,
            status_from=proposal.proposal_status,
            status_to=updated_proposal.proposal_status,
            snapshot_hash=applied_version.snapshot_hash,
            details={"version_id": applied_version.version_id},
        )
        self.session.commit()
        self._write_proposal_artifacts(updated_proposal)
        self._write_memory_version_artifact(applied_version)
        self._write_audit_log_artifact(updated_proposal.investigation_id)
        return applied_version

    def revert_proposal(
        self,
        proposal_id: str,
        *,
        revert_reason: str,
        actor_id: str = "local_user",
    ) -> MemoryStoreVersion:
        proposal = self.get_proposal(proposal_id)
        self._transition_or_error(proposal, RepairStatus.REVERTED, actor=actor_id)
        if proposal.applied_version_id is None:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Proposal has no applied version to revert.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_applied_version",
                    message="Proposal has no applied version to revert.",
                    retryable=False,
                    attempts=1,
                )
            )
        applied_version = self.repository.get_memory_version(proposal.applied_version_id)
        if applied_version is None:
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_applied_version",
                    message="Applied version record is missing.",
                    retryable=False,
                    attempts=1,
                )
            )
        if proposal.reverted_version_id is not None:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Proposal has already been reverted.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="duplicate_revert",
                    message="Proposal has already been reverted.",
                    retryable=False,
                    attempts=1,
                )
            )
        parent_version = (
            self.repository.get_memory_version(applied_version.parent_version_id)
            if applied_version.parent_version_id is not None
            else None
        )
        if parent_version is None:
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_parent_version",
                    message="Pre-repair parent version is missing.",
                    retryable=False,
                    attempts=1,
                )
            )
        active_version = self._current_active_version(proposal.scenario_id)
        if active_version is None or active_version.version_id != applied_version.version_id:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Only the current active applied version can be reverted.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="stale_revert",
                    message="Only the current active applied version can be reverted.",
                    retryable=False,
                    attempts=1,
                )
            )
        applied_version.status = MemoryVersionStatus.REVERTED
        self.repository.save_memory_version(applied_version)
        reverted_version = MemoryStoreVersion(
            version_id=f"version_{uuid4().hex}",
            parent_version_id=applied_version.version_id,
            investigation_id=proposal.investigation_id,
            proposal_id=proposal.proposal_id,
            scenario_id=proposal.scenario_id,
            created_at=datetime.now(timezone.utc),
            created_by=actor_id,
            memory_snapshot=[
                memory.model_copy(deep=True) for memory in parent_version.memory_snapshot
            ],
            snapshot_hash=parent_version.snapshot_hash,
            change_summary=f"Revert proposal {proposal.proposal_id}: {revert_reason}",
            status=MemoryVersionStatus.ACTIVE,
        )
        self.repository.save_memory_version(reverted_version)
        updated_proposal = proposal.model_copy(
            update={
                "proposal_status": RepairStatus.REVERTED,
                "reverted_version_id": reverted_version.version_id,
            },
            deep=True,
        )
        self.repository.save_repair_proposal(updated_proposal)
        self._record_audit(
            proposal=updated_proposal,
            event_type=AuditEventType.PROPOSAL_REVERTED,
            actor=actor_id,
            status_from=proposal.proposal_status,
            status_to=updated_proposal.proposal_status,
            snapshot_hash=reverted_version.snapshot_hash,
            details={"revert_reason": revert_reason, "version_id": reverted_version.version_id},
        )
        self.session.commit()
        self._write_proposal_artifacts(updated_proposal)
        self._write_memory_version_artifact(reverted_version)
        self._write_audit_log_artifact(updated_proposal.investigation_id)
        return reverted_version

    def list_memory_versions(self, scenario_id: str) -> list[MemoryStoreVersion]:
        return self.repository.list_memory_versions_for_scenario(scenario_id)

    def show_memory_version(self, version_id: str) -> MemoryStoreVersion:
        version = self.repository.get_memory_version(version_id)
        if version is None:
            raise ValueError(f"unknown memory version: {version_id}")
        if version.snapshot_hash != self._snapshot_hash(version.memory_snapshot):
            raise ValueError(f"memory version snapshot hash mismatch: {version_id}")
        return version

    def preview_memory_diff(self, proposal_id: str) -> MemoryDiff:
        proposal = self.get_proposal(proposal_id)
        investigation = self.replay_engine.load_investigation(proposal.investigation_id)
        current_version = self._version_for_snapshot_hash(
            scenario_id=proposal.scenario_id,
            snapshot_hash=proposal.evidence_references.memory_snapshot_hash,
        ) or self._get_or_create_base_version(investigation)
        before_snapshot = [
            memory.model_copy(deep=True) for memory in current_version.memory_snapshot
        ]
        after_snapshot = (
            self._apply_repair_to_snapshot(proposal=proposal, snapshot=before_snapshot)
            if proposal.repair_type
            not in {
                RepairType.NO_MEMORY_REPAIR_RECOMMENDED,
                RepairType.ESCALATE_PROMPT_OR_POLICY_REVIEW,
            }
            else [memory.model_copy(deep=True) for memory in before_snapshot]
        )
        diff = self._build_memory_diff(
            mode=MemoryDiffMode.PROPOSAL_PREVIEW,
            proposal_id=proposal.proposal_id,
            scenario_id=proposal.scenario_id,
            investigation_id=proposal.investigation_id,
            from_version_id=current_version.version_id,
            to_version_id=None,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            target_memory_ids=proposal.target_memory_ids,
            evidence_references=[
                proposal.proposal_id,
                proposal.evidence_references.parent_trace_id,
            ],
        )
        self._persist_memory_diff(
            diff,
            scenario_id=proposal.scenario_id,
            investigation_id=proposal.investigation_id,
        )
        return diff

    def get_memory_diff(self, diff_id: str) -> MemoryDiff:
        diff = self.repository.get_memory_diff(diff_id)
        if diff is None:
            raise ValueError(f"unknown memory diff: {diff_id}")
        return diff

    def export_memory_diff(self, diff_id: str, fmt: str) -> str:
        diff = self.get_memory_diff(diff_id)
        if fmt == "json":
            return diff.model_dump_json(indent=2)
        if fmt == "markdown":
            return self._render_memory_diff_markdown(diff)
        raise ValueError(f"unsupported format: {fmt}")

    def compare_memory_versions(self, from_version_id: str, to_version_id: str) -> MemoryDiff:
        left = self.show_memory_version(from_version_id)
        right = self.show_memory_version(to_version_id)
        mode = (
            MemoryDiffMode.REVERTED_VERSION
            if right.proposal_id is not None
            and right.status == MemoryVersionStatus.ACTIVE
            and left.proposal_id == right.proposal_id
            else MemoryDiffMode.APPLIED_VERSION
            if right.proposal_id is not None
            else MemoryDiffMode.VERSION_COMPARISON
        )
        diff = self._build_memory_diff(
            mode=mode,
            proposal_id=right.proposal_id,
            scenario_id=right.scenario_id,
            investigation_id=right.investigation_id,
            from_version_id=left.version_id,
            to_version_id=right.version_id,
            before_snapshot=left.memory_snapshot,
            after_snapshot=right.memory_snapshot,
            target_memory_ids=[],
            evidence_references=[left.version_id, right.version_id],
        )
        self._validate_diff_consistency_with_preview(diff)
        self._persist_memory_diff(
            diff,
            scenario_id=right.scenario_id,
            investigation_id=right.investigation_id,
        )
        return diff

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

    def _allowed_transitions(self) -> dict[RepairStatus, set[RepairStatus]]:
        return {
            RepairStatus.PROPOSED: {RepairStatus.APPROVED, RepairStatus.REJECTED},
            RepairStatus.APPROVED: {RepairStatus.APPLIED},
            RepairStatus.APPLIED: {RepairStatus.REVERTED},
            RepairStatus.REJECTED: set(),
            RepairStatus.REVERTED: set(),
        }

    def _transition_or_error(
        self,
        proposal: RepairProposal,
        target_status: RepairStatus,
        *,
        actor: str,
    ) -> None:
        allowed = self._allowed_transitions()[proposal.proposal_status]
        if target_status not in allowed:
            message = (
                f"Invalid proposal state transition: {proposal.proposal_status.value} -> "
                f"{target_status.value}"
            )
            self._failed_transition(proposal, actor=actor, message=message)
            raise RepairProposalError(
                RepairProposalFailure(
                    code="invalid_state_transition",
                    message=message,
                    retryable=False,
                    attempts=1,
                )
            )

    def _failed_transition(self, proposal: RepairProposal, *, actor: str, message: str) -> None:
        self._record_audit(
            proposal=proposal,
            event_type=AuditEventType.FAILED_TRANSITION,
            actor=actor,
            status_from=proposal.proposal_status,
            status_to=proposal.proposal_status,
            details={"message": message},
        )
        self.session.commit()
        self._write_audit_log_artifact(proposal.investigation_id)

    def _default_evidence_reviewed(self, proposal: RepairProposal) -> list[str]:
        return [
            *proposal.evidence_references.replay_artifact_ids,
            *proposal.evidence_references.contradiction_artifact_ids,
        ]

    def _validate_apply_readiness(
        self,
        proposal: RepairProposal,
        investigation: Investigation,
        actor_id: str,
    ) -> None:
        if proposal.approval_record is None:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Proposal must be explicitly approved before apply.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_approval",
                    message="Proposal must be explicitly approved before apply.",
                    retryable=False,
                    attempts=1,
                )
            )
        known_ids = {memory.memory_id for memory in investigation.original_memory_snapshot}
        unknown_target_ids = [
            memory_id for memory_id in proposal.target_memory_ids if memory_id not in known_ids
        ]
        if unknown_target_ids:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message=f"Unknown target memory IDs: {unknown_target_ids}",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="invalid_target_memory_ids",
                    message=f"Unknown target memory IDs: {unknown_target_ids}",
                    retryable=False,
                    attempts=1,
                )
            )
        missing_artifacts = [
            name
            for name in (
                proposal.evidence_references.replay_artifact_ids
                + proposal.evidence_references.contradiction_artifact_ids
            )
            if not (self._investigation_dir(proposal.investigation_id) / name).exists()
        ]
        if missing_artifacts:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message=f"Evidence artifacts are missing: {missing_artifacts}",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="missing_evidence_references",
                    message=f"Evidence artifacts are missing: {missing_artifacts}",
                    retryable=False,
                    attempts=1,
                )
            )
        if proposal.applied_version_id is not None:
            self._failed_transition(
                proposal,
                actor=actor_id,
                message="Proposal was already applied.",
            )
            raise RepairProposalError(
                RepairProposalFailure(
                    code="duplicate_apply",
                    message="Proposal was already applied.",
                    retryable=False,
                    attempts=1,
                )
            )

    def _get_or_create_base_version(self, investigation: Investigation) -> MemoryStoreVersion:
        current = self._current_active_version(investigation.scenario_id)
        if current is not None:
            return current
        base = MemoryStoreVersion(
            version_id=f"version_{investigation.scenario_id}_root",
            parent_version_id=None,
            investigation_id=investigation.investigation_id,
            proposal_id=None,
            scenario_id=investigation.scenario_id,
            created_at=investigation.created_at,
            created_by="system",
            memory_snapshot=[
                memory.model_copy(deep=True) for memory in investigation.original_memory_snapshot
            ],
            snapshot_hash=self._snapshot_hash(investigation.original_memory_snapshot),
            change_summary="Immutable original investigation snapshot.",
            status=MemoryVersionStatus.ACTIVE,
        )
        self.repository.save_memory_version(base)
        self.session.commit()
        self._write_memory_version_artifact(base)
        return base

    def _current_active_version(self, scenario_id: str) -> MemoryStoreVersion | None:
        active = [
            version
            for version in self.repository.list_memory_versions_for_scenario(scenario_id)
            if version.status == MemoryVersionStatus.ACTIVE
        ]
        if not active:
            return None
        return active[-1]

    def _version_for_snapshot_hash(
        self,
        *,
        scenario_id: str,
        snapshot_hash: str,
    ) -> MemoryStoreVersion | None:
        for version in self.repository.list_memory_versions_for_scenario(scenario_id):
            if version.snapshot_hash == snapshot_hash:
                return version
        return None

    def _apply_repair_to_snapshot(
        self,
        *,
        proposal: RepairProposal,
        snapshot: list[AgentInputMemory],
    ) -> list[AgentInputMemory]:
        updated = [memory.model_copy(deep=True) for memory in snapshot]
        lookup = {memory.memory_id: memory for memory in updated}
        targets = [lookup[memory_id] for memory_id in proposal.target_memory_ids]
        for memory in targets:
            if proposal.repair_type == RepairType.INVALIDATE_MEMORY:
                memory.status = MemoryStatus.INVALID
            elif proposal.repair_type == RepairType.ADD_EXPIRATION_DATE:
                memory.valid_until = self._parse_datetime_field(
                    proposal.proposed_after_state.get("valid_until")
                )
            elif proposal.repair_type == RepairType.MARK_SUPERSEDED:
                memory.status = MemoryStatus.SUPERSEDED
                superseded_by = proposal.proposed_after_state.get(
                    "superseded_by", proposal.proposal_id
                )
                memory.operational_metadata["superseded_by"] = superseded_by
            elif proposal.repair_type == RepairType.CORRECT_ENTITY_ASSOCIATION:
                memory.operational_metadata["previous_entity_id"] = memory.entity_id
                memory.entity_id = proposal.proposed_after_state.get("entity_id", memory.entity_id)
            elif proposal.repair_type == RepairType.MERGE_CONTRADICTORY_MEMORIES:
                memory.operational_metadata["merged_with"] = [
                    target_id
                    for target_id in proposal.target_memory_ids
                    if target_id != memory.memory_id
                ]
                memory.operational_metadata["merge_summary"] = proposal.proposed_after_state.get(
                    "merge_summary",
                    "Merged contradictory memory context.",
                )
            elif proposal.repair_type == RepairType.LOWER_RETRIEVAL_PRIORITY:
                memory.operational_metadata["previous_retrieval_priority"] = (
                    memory.retrieval_priority
                )
                memory.retrieval_priority = int(
                    proposal.proposed_after_state.get(
                        "retrieval_priority", str(memory.retrieval_priority)
                    )
                )
            elif proposal.repair_type == RepairType.REPLACE_WITH_CORRECTED_FACT:
                memory.operational_metadata["previous_content"] = memory.content
                memory.content = proposal.proposed_after_state.get("content", memory.content)
            elif proposal.repair_type == RepairType.ADD_CONTEXT_CONSTRAINT:
                memory.operational_metadata["context_constraint"] = (
                    proposal.proposed_after_state.get(
                        "context_constraint",
                        "Requires additional contextual validation.",
                    )
                )
            elif proposal.repair_type == RepairType.ADD_PRECEDENCE_METADATA:
                memory.operational_metadata["precedence_note"] = proposal.proposed_after_state.get(
                    "precedence_note",
                    "Use explicit precedence review before applying this memory.",
                )
            elif proposal.repair_type == RepairType.REQUIRE_HUMAN_CONFIRMATION:
                memory.operational_metadata["requires_human_confirmation"] = True
                memory.operational_metadata["human_confirmation_note"] = (
                    proposal.proposed_after_state.get(
                        "repair_review_status",
                        "Human confirmation required.",
                    )
                )
        for memory in updated:
            memory.model_validate(memory.model_dump())
        return updated

    def _parse_datetime_field(self, raw_value: str | None) -> datetime | None:
        if raw_value is None:
            return None
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))

    def _change_summary(self, proposal: RepairProposal) -> str:
        targets = (
            ", ".join(proposal.target_memory_ids) if proposal.target_memory_ids else "no targets"
        )
        return f"{proposal.repair_type.value} applied to {targets}"

    def _persist_proposal(self, proposal: RepairProposal) -> None:
        self.repository.save_repair_proposal(proposal)
        self._record_audit(
            proposal=proposal,
            event_type=AuditEventType.PROPOSAL_CREATED,
            actor="system",
            status_from=None,
            status_to=proposal.proposal_status,
            snapshot_hash=proposal.evidence_references.memory_snapshot_hash,
            details={"repair_type": proposal.repair_type.value},
        )
        self.session.commit()
        self._write_proposal_artifacts(proposal)
        self._write_audit_log_artifact(proposal.investigation_id)

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

    def _build_memory_diff(
        self,
        *,
        mode: MemoryDiffMode,
        proposal_id: str | None,
        scenario_id: str,
        investigation_id: str,
        from_version_id: str | None,
        to_version_id: str | None,
        before_snapshot: list[AgentInputMemory],
        after_snapshot: list[AgentInputMemory],
        target_memory_ids: list[str],
        evidence_references: list[str],
    ) -> MemoryDiff:
        before_hash = self._snapshot_hash(before_snapshot)
        after_hash = self._snapshot_hash(after_snapshot)
        before_map = {
            memory.memory_id: memory.model_dump(mode="json") for memory in before_snapshot
        }
        after_map = {memory.memory_id: memory.model_dump(mode="json") for memory in after_snapshot}
        memory_ids = sorted(set(before_map) | set(after_map))
        added_fields: list[MemoryFieldChange] = []
        removed_fields: list[MemoryFieldChange] = []
        changed_fields: list[MemoryFieldChange] = []
        unchanged_fields: list[str] = []
        per_memory: dict[str, dict[str, list[MemoryFieldChange]]] = {}

        for memory_id in memory_ids:
            bucket = per_memory.setdefault(
                memory_id,
                {"added": [], "removed": [], "changed": []},
            )
            before_payload = before_map.get(memory_id, ABSENT)
            after_payload = after_map.get(memory_id, ABSENT)
            diffs = self._collect_field_changes(memory_id, "", before_payload, after_payload)
            if not diffs:
                unchanged_fields.append(memory_id)
                continue
            for change in diffs:
                if change.change_type == MemoryDiffChangeType.ADDED:
                    added_fields.append(change)
                    bucket["added"].append(change)
                elif change.change_type == MemoryDiffChangeType.REMOVED:
                    removed_fields.append(change)
                    bucket["removed"].append(change)
                else:
                    changed_fields.append(change)
                    bucket["changed"].append(change)

        all_changes = [*added_fields, *removed_fields, *changed_fields]
        diff = MemoryDiff(
            diff_id=f"diff_{uuid4().hex}",
            mode=mode,
            proposal_id=proposal_id,
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            target_memory_ids=target_memory_ids,
            added_fields=added_fields,
            removed_fields=removed_fields,
            changed_fields=changed_fields,
            unchanged_fields=unchanged_fields,
            status_changes=[
                change for change in all_changes if change.field_path.endswith("status")
            ],
            validity_changes=[
                change
                for change in all_changes
                if "valid_from" in change.field_path or "valid_until" in change.field_path
            ],
            entity_changes=[
                change for change in all_changes if change.field_path.endswith("entity_id")
            ],
            priority_changes=[
                change for change in all_changes if change.field_path.endswith("retrieval_priority")
            ],
            superseding_relationship_changes=[
                change
                for change in all_changes
                if "supersedes" in change.field_path or "superseded" in change.field_path
            ],
            context_constraint_changes=[
                change
                for change in all_changes
                if "context_constraint" in change.field_path
                or "human_confirmation" in change.field_path
                or "precedence_note" in change.field_path
            ],
            generated_at=datetime.now(timezone.utc),
            snapshot_hash_before=before_hash,
            snapshot_hash_after=after_hash,
            evidence_references=evidence_references,
            frontend_sections=self._build_frontend_sections(per_memory),
        )
        self._validate_diff_hashes(
            diff=diff,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        return diff

    def _collect_field_changes(
        self,
        memory_id: str,
        field_path: str,
        before: Any,
        after: Any,
    ) -> list[MemoryFieldChange]:
        if before == after:
            return []
        if before == ABSENT:
            return [
                self._make_field_change(
                    memory_id=memory_id,
                    field_path=field_path or "memory",
                    before=ABSENT,
                    after=after,
                    change_type=MemoryDiffChangeType.ADDED,
                )
            ]
        if after == ABSENT:
            return [
                self._make_field_change(
                    memory_id=memory_id,
                    field_path=field_path or "memory",
                    before=before,
                    after=ABSENT,
                    change_type=MemoryDiffChangeType.REMOVED,
                )
            ]
        if isinstance(before, dict) and isinstance(after, dict):
            changes: list[MemoryFieldChange] = []
            for key in sorted(set(before) | set(after)):
                next_path = f"{field_path}.{key}" if field_path else key
                changes.extend(
                    self._collect_field_changes(
                        memory_id,
                        next_path,
                        before.get(key, ABSENT),
                        after.get(key, ABSENT),
                    )
                )
            return changes
        if isinstance(before, list) and isinstance(after, list):
            return [
                self._make_field_change(
                    memory_id=memory_id,
                    field_path=field_path,
                    before=before,
                    after=after,
                    change_type=MemoryDiffChangeType.CHANGED,
                )
            ]
        return [
            self._make_field_change(
                memory_id=memory_id,
                field_path=field_path,
                before=before,
                after=after,
                change_type=MemoryDiffChangeType.CHANGED,
            )
        ]

    def _make_field_change(
        self,
        *,
        memory_id: str,
        field_path: str,
        before: Any,
        after: Any,
        change_type: MemoryDiffChangeType,
    ) -> MemoryFieldChange:
        redacted_before = self._redact_secret_value(field_path, before)
        redacted_after = self._redact_secret_value(field_path, after)
        return MemoryFieldChange(
            memory_id=memory_id,
            field_path=field_path,
            before=redacted_before,
            after=redacted_after,
            change_type=change_type,
            risk_level=self._risk_level_for_field(field_path),
            concise_explanation=self._explain_field_change(field_path, change_type),
        )

    def _risk_level_for_field(self, field_path: str) -> MemoryDiffRiskLevel:
        if field_path.endswith("entity_id") or field_path.endswith("content"):
            return MemoryDiffRiskLevel.HIGH
        if (
            "valid_" in field_path
            or "status" in field_path
            or "retrieval_priority" in field_path
            or "supersedes" in field_path
        ):
            return MemoryDiffRiskLevel.MEDIUM
        return MemoryDiffRiskLevel.LOW

    def _explain_field_change(
        self,
        field_path: str,
        change_type: MemoryDiffChangeType,
    ) -> str:
        if change_type == MemoryDiffChangeType.ADDED:
            return f"Adds `{field_path}` to the operational snapshot."
        if change_type == MemoryDiffChangeType.REMOVED:
            return f"Removes `{field_path}` from the operational snapshot."
        return f"Updates `{field_path}` in the operational snapshot."

    def _build_frontend_sections(
        self,
        per_memory: dict[str, dict[str, list[MemoryFieldChange]]],
    ) -> list[MemoryDiffFrontendSection]:
        sections: list[MemoryDiffFrontendSection] = []
        for memory_id in sorted(per_memory):
            bucket = per_memory[memory_id]
            total_changes = sum(len(values) for values in bucket.values())
            if total_changes == 0:
                continue
            sections.append(
                MemoryDiffFrontendSection(
                    memory_id=memory_id,
                    summary=f"{total_changes} structured field change(s) detected.",
                    changed_fields=bucket["changed"],
                    added_fields=bucket["added"],
                    removed_fields=bucket["removed"],
                )
            )
        return sections

    def _validate_diff_hashes(
        self,
        *,
        diff: MemoryDiff,
        before_snapshot: list[AgentInputMemory],
        after_snapshot: list[AgentInputMemory],
    ) -> None:
        before_hash = self._snapshot_hash(before_snapshot)
        after_hash = self._snapshot_hash(after_snapshot)
        if diff.snapshot_hash_before != before_hash or diff.snapshot_hash_after != after_hash:
            raise ValueError("memory diff snapshot hash mismatch")

    def _validate_diff_consistency_with_preview(self, diff: MemoryDiff) -> None:
        if diff.proposal_id is None or diff.mode == MemoryDiffMode.PROPOSAL_PREVIEW:
            return
        previews = [
            preview
            for preview in self.repository.list_memory_diffs_for_proposal(diff.proposal_id)
            if preview.mode == MemoryDiffMode.PROPOSAL_PREVIEW
        ]
        if not previews:
            return
        preview = previews[-1]
        if self._diff_signature(preview) != self._diff_signature(diff):
            raise ValueError("applied diff does not match the stored preview diff")

    def _diff_signature(self, diff: MemoryDiff) -> tuple[tuple[str, str, str, str, str], ...]:
        all_changes = [*diff.added_fields, *diff.removed_fields, *diff.changed_fields]
        return tuple(
            sorted(
                (
                    change.memory_id,
                    change.field_path,
                    json.dumps(change.before, sort_keys=True),
                    json.dumps(change.after, sort_keys=True),
                    change.change_type.value,
                )
                for change in all_changes
            )
        )

    def _redact_secret_value(self, field_path: str, value: Any) -> Any:
        if any(token in field_path.lower() for token in SECRET_FIELD_TOKENS):
            return REDACTED if value != ABSENT else ABSENT
        if isinstance(value, dict):
            return {
                key: self._redact_secret_value(f"{field_path}.{key}" if field_path else key, item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_secret_value(field_path, item) for item in value]
        return value

    def _render_memory_diff_markdown(self, diff: MemoryDiff) -> str:
        lines = [
            "# Memory Diff",
            "",
            "## Summary",
            "",
            f"- Diff ID: `{diff.diff_id}`",
            f"- Mode: `{diff.mode.value}`",
            f"- Proposal ID: `{diff.proposal_id or 'none'}`",
            f"- From version: `{diff.from_version_id or 'none'}`",
            f"- To version: `{diff.to_version_id or 'none'}`",
            f"- Snapshot hash before: `{diff.snapshot_hash_before}`",
            f"- Snapshot hash after: `{diff.snapshot_hash_after}`",
            f"- Changed fields: `{len(diff.changed_fields)}`",
            f"- Added fields: `{len(diff.added_fields)}`",
            f"- Removed fields: `{len(diff.removed_fields)}`",
            "",
            "## Changed Memories",
            "",
        ]
        if not diff.frontend_sections:
            lines.append("No memory changes proposed.")
        for section in diff.frontend_sections:
            lines.extend(["", f"### Memory: `{section.memory_id}`", ""])
            for label, changes in (
                ("Added fields", section.added_fields),
                ("Removed fields", section.removed_fields),
                ("Changed fields", section.changed_fields),
            ):
                if not changes:
                    continue
                lines.extend([f"#### {label}", ""])
                for change in changes:
                    lines.extend(
                        [
                            f"- {change.field_path}: {self._markdown_value(change.before)}",
                            f"- {change.field_path}: {self._markdown_value(change.after)}",
                            f"- Risk: `{change.risk_level.value}`",
                            f"- Note: {change.concise_explanation}",
                            "",
                        ]
                    )
        lines.extend(["## Risk Notes", ""])
        risk_notes = [
            change
            for change in [
                *diff.changed_fields,
                *diff.added_fields,
                *diff.removed_fields,
            ]
        ]
        if not risk_notes:
            lines.append("No memory mutation risk. This diff is informational only.")
        else:
            for change in risk_notes:
                lines.append(
                    (
                        f"- `{change.memory_id}` `{change.field_path}` is "
                        f"`{change.risk_level.value}` risk."
                    )
                )
        lines.extend(["", "## Evidence References", ""])
        if not diff.evidence_references:
            lines.append("- None")
        else:
            lines.extend([f"- `{reference}`" for reference in diff.evidence_references])
        return "\n".join(lines)

    def _markdown_value(self, value: Any) -> str:
        if value == ABSENT:
            return "`<absent>`"
        if value is None:
            return "`null`"
        if isinstance(value, (dict, list)):
            return f"`{json.dumps(value, sort_keys=True)}`"
        return f"`{value}`"

    def _record_audit(
        self,
        *,
        proposal: RepairProposal,
        event_type: AuditEventType,
        actor: str,
        status_from: RepairStatus | None,
        status_to: RepairStatus | None,
        snapshot_hash: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.repository.save_audit_log(
            AuditLogEntry(
                audit_id=f"audit_{uuid4().hex}",
                investigation_id=proposal.investigation_id,
                proposal_id=proposal.proposal_id,
                scenario_id=proposal.scenario_id,
                event_type=event_type,
                actor=actor,
                timestamp=datetime.now(timezone.utc),
                status_from=status_from,
                status_to=status_to,
                snapshot_hash=snapshot_hash,
                details=details or {},
            )
        )

    def _persist_memory_diff(
        self,
        diff: MemoryDiff,
        *,
        scenario_id: str,
        investigation_id: str,
    ) -> None:
        self.repository.save_memory_diff(
            diff,
            scenario_id=scenario_id,
            investigation_id=investigation_id,
        )
        self.session.commit()
        self._write_memory_diff_artifacts(diff, investigation_id=investigation_id)

    def _write_proposal_artifacts(self, proposal: RepairProposal) -> None:
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

    def _write_memory_version_artifact(self, version: MemoryStoreVersion) -> None:
        versions_dir = self._investigation_dir(version.investigation_id) / "memory-versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        (versions_dir / f"{version.version_id}.json").write_text(
            version.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _write_memory_diff_artifacts(self, diff: MemoryDiff, *, investigation_id: str) -> None:
        diffs_dir = self._investigation_dir(investigation_id) / "memory-diffs"
        diffs_dir.mkdir(parents=True, exist_ok=True)
        (diffs_dir / f"{diff.diff_id}.json").write_text(
            diff.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (diffs_dir / f"{diff.diff_id}.md").write_text(
            self._render_memory_diff_markdown(diff),
            encoding="utf-8",
        )

    def _write_audit_log_artifact(self, investigation_id: str) -> None:
        audit_entries = self.repository.list_audit_logs_for_investigation(investigation_id)
        audit_path = self._investigation_dir(investigation_id) / "audit-log.json"
        audit_path.write_text(
            json.dumps([entry.model_dump(mode="json") for entry in audit_entries], indent=2),
            encoding="utf-8",
        )

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
