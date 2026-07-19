from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ScenarioRecord(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)


class TraceRecord(Base):
    __tablename__ = "traces"

    trace_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, index=True, nullable=True)
    selected_action: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RepairProposalRecord(Base):
    __tablename__ = "repair_proposals"

    proposal_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ApprovalRecordModel(Base):
    __tablename__ = "approval_records"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String, index=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MemoryVersionRecord(Base):
    __tablename__ = "memory_versions"

    version_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    investigation_id: Mapped[str] = mapped_column(String, index=True)
    proposal_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    investigation_id: Mapped[str] = mapped_column(String, index=True)
    proposal_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MemoryDiffRecord(Base):
    __tablename__ = "memory_diffs"

    diff_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    investigation_id: Mapped[str] = mapped_column(String, index=True)
    proposal_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    from_version_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    to_version_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    mode: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class BenchmarkRunRecord(Base):
    __tablename__ = "benchmark_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    total_scenarios: Mapped[int] = mapped_column(Integer)
    passed_scenarios: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class VerificationArtifactRecord(Base):
    __tablename__ = "verification_artifacts"

    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
