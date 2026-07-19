from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from memory_mri.db.models import (
    BenchmarkRunRecord,
    MemoryRecord,
    RepairProposalRecord,
    ScenarioRecord,
    TraceRecord,
    VerificationArtifactRecord,
)
from memory_mri.schemas import BenchmarkCase, ExecutionTrace, RepairProposal


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
            "benchmark_runs": self.session.query(BenchmarkRunRecord).count(),
            "verification_artifacts": self.session.query(VerificationArtifactRecord).count(),
        }
