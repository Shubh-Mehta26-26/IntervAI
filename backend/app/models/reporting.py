from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class Report(Record, Base):
    __tablename__ = "reports"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    interview_id: Mapped[UUID]
    latest_version: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        ForeignKeyConstraint(
            ["interview_id", "candidate_id"],
            ["interviews.id", "interviews.candidate_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("candidate_id", "interview_id", name="uq_report_candidate_interview"),
        UniqueConstraint("id", "candidate_id", name="uq_report_owner"),
        CheckConstraint("latest_version >= 0", name="ck_report_version"),
    )


class ReportVersion(Record, Base):
    __tablename__ = "report_versions"
    report_id: Mapped[UUID]
    candidate_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["report_id", "candidate_id"],
            ["reports.id", "reports.candidate_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("report_id", "version", name="uq_report_version"),
        UniqueConstraint("report_id", "source_fingerprint", name="uq_report_fingerprint"),
        CheckConstraint("version > 0 AND schema_version > 0", name="ck_report_version_positive"),
        Index("ix_report_versions_candidate", "candidate_id", "generated_at"),
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    service: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    __table_args__ = (CheckConstraint("status IN ('running','degraded')", name="ck_worker_status"),)
