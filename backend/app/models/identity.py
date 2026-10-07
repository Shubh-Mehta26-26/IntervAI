from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), server_default="candidate")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        CheckConstraint("role IN ('candidate','recruiter','admin')", name="ck_users_role"),
    )


class Session(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    csrf_hash: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),)


class Candidate(Record, Base):
    __tablename__ = "candidates"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(160))
    headline: Mapped[str | None] = mapped_column(String(200))
    biography: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC")
    experience_months: Mapped[int] = mapped_column(Integer, server_default="0")
    memory_revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    revision: Mapped[int] = mapped_column(Integer, server_default="0")
    career_interests: Mapped[list[str]] = mapped_column(ARRAY(String(80)), server_default="{}")
    __table_args__ = (
        CheckConstraint("experience_months BETWEEN 0 AND 720", name="ck_candidate_experience"),
        CheckConstraint("revision >= 0 AND memory_revision >= 0", name="ck_candidate_revisions"),
    )


class CandidateGoal(Record, Base):
    __tablename__ = "candidate_goals"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    role_title: Mapped[str] = mapped_column(String(120))
    priority: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    __table_args__ = (
        UniqueConstraint("candidate_id", "role_title", name="uq_candidate_goal_role"),
        CheckConstraint("priority >= 0", name="ck_goal_priority"),
    )


class Education(Record, Base):
    __tablename__ = "candidate_education"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(160))
    qualification: Mapped[str] = mapped_column(String(160))
    field_of_study: Mapped[str | None] = mapped_column(String(160))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_education_dates"),)


class Experience(Record, Base):
    __tablename__ = "candidate_experience"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    organization: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_experience_dates"),)


class CandidatePreferences(Record, Base):
    __tablename__ = "candidate_preferences"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), unique=True
    )
    interview_mode: Mapped[str] = mapped_column(String(20), server_default="text")
    interview_duration_minutes: Mapped[int] = mapped_column(Integer, server_default="20")
    locale: Mapped[str] = mapped_column(String(20), server_default="en")
    __table_args__ = (
        CheckConstraint("interview_mode IN ('text','voice')", name="ck_preferences_mode"),
        CheckConstraint(
            "interview_duration_minutes IN (10,20,30,45,60)", name="ck_preferences_duration"
        ),
    )


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    bucket_key: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    __table_args__ = (
        Index("ix_auth_rate_window", "window_start"),
        CheckConstraint("attempts > 0", name="ck_auth_rate_attempts"),
    )
