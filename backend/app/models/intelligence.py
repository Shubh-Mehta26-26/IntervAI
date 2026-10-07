from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class Skill(Record, Base):
    __tablename__ = "skills"
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))


class Resume(Record, Base):
    __tablename__ = "resumes"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    parsing_status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(String(500))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict | None] = mapped_column(JSONB)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_id: Mapped[UUID | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("candidate_id", "version"),
        CheckConstraint(
            "status IN ('uploaded','processing','parsed','failed')", name="ck_resume_status"
        ),
        CheckConstraint(
            "parsing_status IN ('pending','processing','parsed','failed')",
            name="ck_resume_parse_status",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_resume_size"),
    )


class ResumeSkill(Base):
    __tablename__ = "resume_skills"
    resume_id: Mapped[UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True, index=True)
    evidence: Mapped[list] = mapped_column(JSONB)


class JobDescription(Record, Base):
    __tablename__ = "job_descriptions"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    company: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="pasted")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    analyzed_version: Mapped[int | None] = mapped_column(Integer)
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("status IN ('draft','analyzed')", name="ck_job_status"),
        UniqueConstraint("id", "candidate_id", name="uq_job_description_owner"),
    )


class JobSkill(Base):
    __tablename__ = "job_skills"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True, index=True)
    requirement: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[list] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint(
            "requirement IN ('required','preferred','unspecified')", name="ck_job_skill_requirement"
        ),
    )


class CandidateJobMatch(Record, Base):
    __tablename__ = "candidate_job_matches"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="CASCADE"), unique=True
    )
    resume_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
