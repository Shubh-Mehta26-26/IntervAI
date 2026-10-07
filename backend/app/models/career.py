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


class CareerRole(Record, Base):
    __tablename__ = "career_roles"
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(600))
    requirements: Mapped[list] = mapped_column(JSONB)
    responsibilities: Mapped[list] = mapped_column(JSONB)
    provenance: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer)


class CareerProfile(Record, Base):
    __tablename__ = "career_profiles"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), unique=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    dismissed_roles: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = (CheckConstraint("revision >= 0", name="ck_career_profile_revision"),)


class CareerAnalysis(Record, Base):
    __tablename__ = "career_analyses"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_career_analysis_version"),
        UniqueConstraint("candidate_id", "fingerprint", name="uq_career_analysis_snapshot"),
        UniqueConstraint("id", "candidate_id", name="uq_career_analysis_owner"),
        CheckConstraint("version > 0", name="ck_career_analysis_version"),
        Index("ix_career_analysis_candidate_time", "candidate_id", "created_at"),
    )


class CareerRequest(Record, Base):
    __tablename__ = "career_requests"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    request_key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    analysis_id: Mapped[UUID]
    __table_args__ = (
        UniqueConstraint("candidate_id", "request_key", name="uq_career_request_key"),
        ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
    )


class CareerChoice(Record, Base):
    __tablename__ = "career_choices"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    analysis_id: Mapped[UUID]
    role_slug: Mapped[str] = mapped_column(String(80))
    skill: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("analysis_id", "role_slug", "skill", name="uq_career_choice"),
        CheckConstraint(
            "state IN ('pursue','dismissed') AND revision >= 0", name="ck_career_choice_state"
        ),
    )


class CareerAdvice(Record, Base):
    __tablename__ = "career_advice"
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    analysis_id: Mapped[UUID] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    claim_id: Mapped[UUID]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    use_rag: Mapped[bool]
    content: Mapped[dict | None] = mapped_column(JSONB)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    retrieval_status: Mapped[str] = mapped_column(String(40), default="not_requested")
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending','completed','failed') AND attempts BETWEEN 1 AND 3",
            name="ck_career_advice_state",
        ),
    )
