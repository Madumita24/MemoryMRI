from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from memory_mri.db.models import (
    ApprovalRecordModel,
    AuditLogRecord,
    BenchmarkRunRecord,
    MemoryDiffRecord,
    MemoryRecord,
    MemoryVersionRecord,
    RepairProposalRecord,
    ScenarioRecord,
    TraceRecord,
    VerificationArtifactRecord,
)
from memory_mri.schemas import (
    ApprovalRecord,
    AuditLogEntry,
    BenchmarkCase,
    ExecutionTrace,
    MemoryDiff,
    MemoryStoreVersion,
    RepairProposal,
)


class BenchmarkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_case(self, case: BenchmarkCase) -> None:
        scenario = case.scenario
        self.session.merge(
            ScenarioRecord(
                id=scenario.id,
                domain=scenario.domain.value,
                title=scenario.title,
                payload_json=scenario.model_dump_json(),
            )
        )
        for memory in case.memories:
            self.session.merge(
                MemoryRecord(
                    id=memory.id,
                    domain=memory.domain.value,
                    entity_id=memory.entity_id,
                    payload_json=memory.model_dump_json(),
                )
            )

    def save_trace(self, trace: ExecutionTrace) -> None:
        self.session.add(
            TraceRecord(
                trace_id=trace.trace_id,
                scenario_id=trace.scenario_id,
                run_id=trace.run_id,
                passed=trace.passed if trace.passed is not None else False,
                selected_action=trace.selected_action,
                payload_json=trace.model_dump_json(),
            )
        )

    def save_benchmark_run(
        self, run_id: str, total_scenarios: int, passed_scenarios: int, payload: dict[str, Any]
    ) -> None:
        self.session.add(
            BenchmarkRunRecord(
                run_id=run_id,
                total_scenarios=total_scenarios,
                passed_scenarios=passed_scenarios,
                payload_json=json.dumps(payload, indent=2),
            )
        )

    def save_repair_proposal(self, proposal: RepairProposal) -> None:
        self.session.merge(
            RepairProposalRecord(
                proposal_id=proposal.proposal_id,
                scenario_id=proposal.scenario_id,
                status=proposal.proposal_status.value,
                payload_json=proposal.model_dump_json(),
            )
        )

    def save_approval_record(self, approval: ApprovalRecord, scenario_id: str) -> None:
        self.session.add(
            ApprovalRecordModel(
                approval_id=f"approval_{approval.proposal_id}",
                proposal_id=approval.proposal_id,
                scenario_id=scenario_id,
                payload_json=approval.model_dump_json(),
            )
        )

    def save_memory_version(self, version: MemoryStoreVersion) -> None:
        self.session.merge(
            MemoryVersionRecord(
                version_id=version.version_id,
                scenario_id=version.scenario_id,
                investigation_id=version.investigation_id,
                proposal_id=version.proposal_id,
                status=version.status.value,
                payload_json=version.model_dump_json(),
            )
        )

    def save_audit_log(self, entry: AuditLogEntry) -> None:
        self.session.add(
            AuditLogRecord(
                audit_id=entry.audit_id,
                scenario_id=entry.scenario_id,
                investigation_id=entry.investigation_id,
                proposal_id=entry.proposal_id,
                event_type=entry.event_type.value,
                actor=entry.actor,
                payload_json=entry.model_dump_json(),
            )
        )

    def save_memory_diff(
        self,
        diff: MemoryDiff,
        *,
        scenario_id: str,
        investigation_id: str,
    ) -> None:
        self.session.merge(
            MemoryDiffRecord(
                diff_id=diff.diff_id,
                scenario_id=scenario_id,
                investigation_id=investigation_id,
                proposal_id=diff.proposal_id,
                from_version_id=diff.from_version_id,
                to_version_id=diff.to_version_id,
                mode=diff.mode.value,
                payload_json=diff.model_dump_json(),
            )
        )

    def get_trace(self, trace_id: str) -> ExecutionTrace | None:
        record = self.session.get(TraceRecord, trace_id)
        if record is None:
            return None
        return ExecutionTrace.model_validate_json(record.payload_json)

    def get_repair_proposal(self, proposal_id: str) -> RepairProposal | None:
        record = self.session.get(RepairProposalRecord, proposal_id)
        if record is None:
            return None
        return RepairProposal.model_validate_json(record.payload_json)

    def get_memory_version(self, version_id: str) -> MemoryStoreVersion | None:
        record = self.session.get(MemoryVersionRecord, version_id)
        if record is None:
            return None
        return MemoryStoreVersion.model_validate_json(record.payload_json)

    def get_memory_diff(self, diff_id: str) -> MemoryDiff | None:
        record = self.session.get(MemoryDiffRecord, diff_id)
        if record is None:
            return None
        return MemoryDiff.model_validate_json(record.payload_json)

    def list_traces(self) -> list[ExecutionTrace]:
        return [
            ExecutionTrace.model_validate_json(record.payload_json)
            for record in self.session.query(TraceRecord).order_by(TraceRecord.created_at).all()
        ]

    def list_traces_for_scenario(self, scenario_id: str) -> list[ExecutionTrace]:
        return [
            ExecutionTrace.model_validate_json(record.payload_json)
            for record in self.session.query(TraceRecord)
            .filter(TraceRecord.scenario_id == scenario_id)
            .order_by(TraceRecord.created_at)
            .all()
        ]

    def list_failed_traces(self) -> list[ExecutionTrace]:
        return [
            ExecutionTrace.model_validate_json(record.payload_json)
            for record in self.session.query(TraceRecord)
            .filter(TraceRecord.passed.is_(False))
            .order_by(TraceRecord.created_at)
            .all()
        ]

    def list_repair_proposals(self) -> list[RepairProposal]:
        return [
            RepairProposal.model_validate_json(record.payload_json)
            for record in self.session.query(RepairProposalRecord).all()
        ]

    def list_memory_versions(self) -> list[MemoryStoreVersion]:
        return [
            MemoryStoreVersion.model_validate_json(record.payload_json)
            for record in self.session.query(MemoryVersionRecord)
            .order_by(MemoryVersionRecord.created_at)
            .all()
        ]

    def list_memory_versions_for_scenario(self, scenario_id: str) -> list[MemoryStoreVersion]:
        return [
            MemoryStoreVersion.model_validate_json(record.payload_json)
            for record in self.session.query(MemoryVersionRecord)
            .filter(MemoryVersionRecord.scenario_id == scenario_id)
            .order_by(MemoryVersionRecord.created_at)
            .all()
        ]

    def list_audit_logs_for_proposal(self, proposal_id: str) -> list[AuditLogEntry]:
        return [
            AuditLogEntry.model_validate_json(record.payload_json)
            for record in self.session.query(AuditLogRecord)
            .filter(AuditLogRecord.proposal_id == proposal_id)
            .order_by(AuditLogRecord.created_at)
            .all()
        ]

    def list_audit_logs_for_investigation(self, investigation_id: str) -> list[AuditLogEntry]:
        return [
            AuditLogEntry.model_validate_json(record.payload_json)
            for record in self.session.query(AuditLogRecord)
            .filter(AuditLogRecord.investigation_id == investigation_id)
            .order_by(AuditLogRecord.created_at)
            .all()
        ]

    def list_memory_diffs_for_proposal(self, proposal_id: str) -> list[MemoryDiff]:
        return [
            MemoryDiff.model_validate_json(record.payload_json)
            for record in self.session.query(MemoryDiffRecord)
            .filter(MemoryDiffRecord.proposal_id == proposal_id)
            .order_by(MemoryDiffRecord.created_at)
            .all()
        ]

    def list_repair_proposals_for_investigation(
        self, investigation_id: str
    ) -> list[RepairProposal]:
        proposals = [
            proposal
            for proposal in self.list_repair_proposals()
            if proposal.investigation_id == investigation_id
        ]
        return sorted(proposals, key=lambda proposal: proposal.created_at)

    def list_tables(self) -> dict[str, int]:
        return {
            "memories": self.session.query(MemoryRecord).count(),
            "scenarios": self.session.query(ScenarioRecord).count(),
            "traces": self.session.query(TraceRecord).count(),
            "repair_proposals": self.session.query(RepairProposalRecord).count(),
            "approval_records": self.session.query(ApprovalRecordModel).count(),
            "memory_versions": self.session.query(MemoryVersionRecord).count(),
            "audit_logs": self.session.query(AuditLogRecord).count(),
            "memory_diffs": self.session.query(MemoryDiffRecord).count(),
            "benchmark_runs": self.session.query(BenchmarkRunRecord).count(),
            "verification_artifacts": self.session.query(VerificationArtifactRecord).count(),
        }
