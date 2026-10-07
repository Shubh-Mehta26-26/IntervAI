"""Observable visual events only; never answer, memory, or learning evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record

EVENT_TYPES = (
    "CANDIDATE_PRESENT",
    "CANDIDATE_ABSENT",
    "MULTIPLE_PERSONS_DETECTED",
    "PHONE_DETECTED",
    "CAMERA_INTERRUPTED",
    "CAMERA_ORIENTATION_CHANGED",
)


class VisionSession(Record, Base):
    __tablename__ = "vision_sessions"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    revision: Mapped[int] = mapped_column(Integer, server_default="0")
    sequence: Mapped[int] = mapped_column(Integer, server_default="-1")
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_sequence: Mapped[int | None] = mapped_column(Integer)
    processing_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    aggregate: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    __table_args__ = (
        CheckConstraint("revision >= 0 AND sequence >= -1", name="ck_vision_revision"),
    )


class IntegrityEvent(Record, Base):
    __tablename__ = "integrity_events"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    interview_id: Mapped[UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("vision_sessions.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    detector: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CANDIDATE_PRESENT','CANDIDATE_ABSENT','MULTIPLE_PERSONS_DETECTED','PHONE_DETECTED','CAMERA_INTERRUPTED','CAMERA_ORIENTATION_CHANGED')",
            name="ck_integrity_type",
        ),
        CheckConstraint("severity IN ('INFO','NOTICE','REVIEW')", name="ck_integrity_severity"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_integrity_confidence",
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_integrity_duration"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_integrity_time"),
        Index("ix_integrity_candidate", "candidate_id"),
        Index("ix_integrity_interview_time", "interview_id", "started_at"),
        Index("ix_integrity_type_time", "event_type", "started_at"),
    )
