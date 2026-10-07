from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class CandidateMemory(Record, Base):
    __tablename__ = "candidate_memory"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    subject_key: Mapped[str] = mapped_column(String(240))
    subject: Mapped[str] = mapped_column(String(240))
    topic: Mapped[str] = mapped_column(String(120))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    interview_count: Mapped[int] = mapped_column(Integer, default=0)
    mean_correctness: Mapped[float | None]
    evidence_strength: Mapped[float] = mapped_column(default=0.0)
    trend: Mapped[str] = mapped_column(String(20), default="insufficient")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("candidate_id", "kind", "subject_key", name="uq_memory_subject"),
        UniqueConstraint("id", "candidate_id", name="uq_memory_owner"),
        CheckConstraint(
            "kind IN ('skill','topic','concept','strength','weakness','misconception')",
            name="ck_memory_kind",
        ),
        Index("ix_memory_candidate_seen", "candidate_id", "last_seen"),
    )


class MemoryEvidence(Record, Base):
    __tablename__ = "memory_evidence"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    memory_id: Mapped[UUID]
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_evaluations.id", ondelete="CASCADE")
    )
    root_question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE")
    )
    interview_id: Mapped[UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    correctness: Mapped[float]
    confidence: Mapped[float]
    grounded: Mapped[bool] = mapped_column(Boolean)
    assisted: Mapped[bool] = mapped_column(Boolean)
    question_hash: Mapped[str] = mapped_column(String(64))
    weak: Mapped[bool] = mapped_column(Boolean)
    strong: Mapped[bool] = mapped_column(Boolean)
    signals: Mapped[list] = mapped_column(JSONB)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        ForeignKeyConstraint(
            ["memory_id", "candidate_id"],
            ["candidate_memory.id", "candidate_memory.candidate_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("memory_id", "evaluation_id", name="uq_memory_evaluation"),
        CheckConstraint(
            "correctness BETWEEN 0 AND 1 AND confidence BETWEEN 0 AND 1",
            name="ck_memory_evidence_scales",
        ),
        Index("ix_memory_evidence_history", "candidate_id", "memory_id", "observed_at"),
        Index("ix_memory_evidence_evaluation", "evaluation_id"),
    )


class KnowledgeGap(Record, Base):
    __tablename__ = "knowledge_gaps"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    memory_id: Mapped[UUID] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String(20), default="observed")
    weakness_index: Mapped[float] = mapped_column(default=0.0)
    independent_count: Mapped[int] = mapped_column(Integer, default=0)
    weak_interview_count: Mapped[int] = mapped_column(Integer, default=0)
    baseline_correctness: Mapped[float | None]
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        ForeignKeyConstraint(
            ["memory_id", "candidate_id"],
            ["candidate_memory.id", "candidate_memory.candidate_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('observed','confirmed','learning','improving','resolved')",
            name="ck_gap_status",
        ),
        Index("ix_gaps_candidate_status", "candidate_id", "status", "last_seen"),
    )


class GapTransition(Record, Base):
    __tablename__ = "gap_transitions"
    gap_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_gaps.id", ondelete="CASCADE"), index=True
    )
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_evaluations.id", ondelete="CASCADE")
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        UniqueConstraint("gap_id", "evaluation_id", name="uq_gap_transition_operation"),
    )
