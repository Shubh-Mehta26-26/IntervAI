from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class RecruiterJob(Record, Base):
    __tablename__ = "recruiter_jobs"
    recruiter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(160))
    company: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(default=1)
    requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        UniqueConstraint("id", "recruiter_user_id", name="uq_recruiter_job_owner"),
        CheckConstraint("status IN ('active','paused','closed')", name="ck_recruiter_job_status"),
        CheckConstraint("version > 0", name="ck_recruiter_job_version"),
        Index("ix_recruiter_jobs_status_created", "status", "created_at"),
    )


class RecruiterApplication(Record, Base):
    __tablename__ = "recruiter_applications"
    recruiter_user_id: Mapped[UUID]
    recruiter_job_id: Mapped[UUID]
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    candidate_job_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(16), default="applied")
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        ForeignKeyConstraint(
            ["recruiter_job_id", "recruiter_user_id"],
            ["recruiter_jobs.id", "recruiter_jobs.recruiter_user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["candidate_job_id", "candidate_id"],
            ["job_descriptions.id", "job_descriptions.candidate_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("candidate_id", "recruiter_job_id", name="uq_application_candidate_job"),
        UniqueConstraint("id", "candidate_id", "recruiter_user_id", name="uq_application_owner"),
        CheckConstraint("status IN ('applied','withdrawn','closed')", name="ck_application_status"),
        CheckConstraint("consent_version > 0", name="ck_application_consent_version"),
        Index("ix_recruiter_applications_owner", "recruiter_user_id", "recruiter_job_id", "status"),
        Index("ix_recruiter_applications_candidate", "candidate_id", "created_at"),
    )


class AdminAudit(Record, Base):
    __tablename__ = "admin_audit"
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID | None]
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (Index("ix_admin_audit_created", "created_at"),)
