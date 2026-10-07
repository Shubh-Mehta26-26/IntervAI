from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class LearningPlan(Record, Base):
    __tablename__ = "learning_plans"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="SET NULL")
    )
    request_key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(240))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[float]
    priority_reasons: Mapped[list] = mapped_column(JSONB)
    context: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("candidate_id", "request_key", name="uq_learning_plan_request"),
        UniqueConstraint("candidate_id", "fingerprint", name="uq_learning_plan_fingerprint"),
        CheckConstraint(
            "status IN ('active','completed','archived')", name="ck_learning_plan_status"
        ),
        Index("ix_learning_plan_candidate_created", "candidate_id", "created_at"),
    )


class LearningTarget(Record, Base):
    __tablename__ = "learning_targets"
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("learning_plans.id", ondelete="CASCADE"))
    gap_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_gaps.id", ondelete="CASCADE"))
    memory_id: Mapped[UUID] = mapped_column(ForeignKey("candidate_memory.id", ondelete="CASCADE"))
    baseline_evidence_ids: Mapped[list] = mapped_column(JSONB)
    baseline: Mapped[dict] = mapped_column(JSONB)
    priority: Mapped[float]
    reasons: Mapped[list] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("plan_id", "gap_id", name="uq_learning_target"),)


class LearningItem(Record, Base):
    __tablename__ = "learning_items"
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("learning_plans.id", ondelete="CASCADE"))
    target_id: Mapped[UUID] = mapped_column(ForeignKey("learning_targets.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    topic: Mapped[str] = mapped_column(String(120))
    concept: Mapped[str] = mapped_column(String(240))
    objective: Mapped[str] = mapped_column(Text)
    order_reason: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    effort_minutes: Mapped[int] = mapped_column(Integer, default=15)
    resource_type: Mapped[str] = mapped_column(String(24), default="concept_check")
    content: Mapped[dict] = mapped_column(JSONB)
    content_revision: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("plan_id", "ordinal", name="uq_learning_item_order"),
        CheckConstraint(
            "status IN ('pending','in_progress','completed')", name="ck_learning_item_status"
        ),
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5 AND effort_minutes > 0", name="ck_learning_item_effort"
        ),
    )


class LearningAction(Record, Base):
    __tablename__ = "learning_actions"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("learning_plans.id", ondelete="CASCADE"))
    item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_items.id", ondelete="CASCADE")
    )
    gap_id: Mapped[UUID | None] = mapped_column(ForeignKey("knowledge_gaps.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (Index("ix_learning_actions_plan_created", "plan_id", "created_at"),)


class LearningAttempt(Record, Base):
    __tablename__ = "learning_attempts"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE")
    )
    item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_items.id", ondelete="CASCADE")
    )
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    parent_interview_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="SET NULL")
    )
    request_key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    targets: Mapped[list] = mapped_column(JSONB)
    comparison: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("candidate_id", "request_key", name="uq_learning_attempt_request"),
        CheckConstraint("kind IN ('practice','retry')", name="ck_learning_attempt_kind"),
        Index("ix_learning_attempt_candidate_created", "candidate_id", "created_at"),
    )


class LearningRequest(Record, Base):
    """Retain replay keys even when multiple clicks reuse an existing record."""

    __tablename__ = "learning_requests"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    request_key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE")
    )
    attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_attempts.id", ondelete="CASCADE")
    )
    __table_args__ = (
        UniqueConstraint("candidate_id", "request_key", name="uq_learning_request_key"),
        CheckConstraint(
            "(plan_id IS NULL) <> (attempt_id IS NULL)", name="ck_learning_request_result"
        ),
    )
