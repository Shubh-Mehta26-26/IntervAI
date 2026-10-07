from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class CodingProblem(Record, Base):
    __tablename__ = "coding_problems"
    candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str | None] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(120))
    skills: Mapped[list] = mapped_column(JSONB)
    constraints: Mapped[list] = mapped_column(JSONB)
    input_format: Mapped[str] = mapped_column(Text)
    output_format: Mapped[str] = mapped_column(Text)
    examples: Mapped[list] = mapped_column(JSONB)
    starter_code: Mapped[dict] = mapped_column(JSONB)
    supported_languages: Mapped[list] = mapped_column(JSONB)
    time_ms: Mapped[int] = mapped_column(Integer, default=1000)
    memory_mb: Mapped[int] = mapped_column(Integer, default=128)
    provenance: Mapped[dict] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(String(24), default="draft")
    reference_solutions: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5 AND time_ms BETWEEN 100 AND 3000 AND memory_mb BETWEEN 32 AND 256",
            name="ck_coding_problem_limits",
        ),
        CheckConstraint(
            "validation_status IN ('draft','validating','validated','rejected')",
            name="ck_coding_problem_validation",
        ),
    )


class CodingTestCase(Record, Base):
    __tablename__ = "coding_test_cases"
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("coding_problems.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    hidden: Mapped[bool]
    input: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("problem_id", "ordinal", name="uq_coding_case_ordinal"),)


class CodingSubmission(Record, Base):
    __tablename__ = "coding_submissions"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), index=True
    )
    problem_id: Mapped[UUID] = mapped_column(ForeignKey("coding_problems.id"))
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_jobs.id", ondelete="CASCADE"), unique=True
    )
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="SET NULL"), unique=True
    )
    language: Mapped[str] = mapped_column(String(20))
    source_code: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    submission_number: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), default="SUBMITTED")
    execution_status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    idempotency_key: Mapped[UUID]
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSONB)
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("interview_id", "idempotency_key", name="uq_coding_idempotency"),
        UniqueConstraint("question_id", "submission_number", name="uq_coding_submission_number"),
        CheckConstraint(
            "language IN ('python','cpp','java') AND mode IN ('run','submit')",
            name="ck_coding_language_mode",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED','JUDGING','ACCEPTED','WRONG_ANSWER','PARTIAL','ERROR')",
            name="ck_coding_submission_status",
        ),
        CheckConstraint(
            "execution_status IN ('QUEUED','RUNNING','COMPLETED','COMPILE_ERROR','RUNTIME_ERROR','TIMEOUT','MEMORY_LIMIT','OUTPUT_LIMIT','SYSTEM_ERROR','CANCELLED')",
            name="ck_coding_execution_status",
        ),
        CheckConstraint(
            "octet_length(source_code) BETWEEN 1 AND 32768 AND submission_number > 0",
            name="ck_coding_source_number",
        ),
    )
