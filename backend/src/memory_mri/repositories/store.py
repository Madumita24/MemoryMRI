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
from memory_mri.schemas import BenchmarkCase, ExecutionTrace


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
                passed=trace.passed,
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

    def get_trace(self, trace_id: str) -> ExecutionTrace | None:
        record = self.session.get(TraceRecord, trace_id)
        if record is None:
            return None
        return ExecutionTrace.model_validate_json(record.payload_json)

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

    def list_tables(self) -> dict[str, int]:
        return {
            "memories": self.session.query(MemoryRecord).count(),
            "scenarios": self.session.query(ScenarioRecord).count(),
            "traces": self.session.query(TraceRecord).count(),
            "repair_proposals": self.session.query(RepairProposalRecord).count(),
            "benchmark_runs": self.session.query(BenchmarkRunRecord).count(),
            "verification_artifacts": self.session.query(VerificationArtifactRecord).count(),
        }
