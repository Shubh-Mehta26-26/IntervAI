from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record


class Interview(Record, Base):
    __tablename__ = "interviews"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="SET NULL"), index=True
    )
    resume_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), index=True
    )
    interview_type: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    question_limit: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    configuration: Mapped[dict] = mapped_column(JSONB)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    current_question: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        UniqueConstraint("id", "candidate_id", name="uq_interview_owner"),
        CheckConstraint(
            "interview_type IN ('technical','project','behavioral','mixed','coding')",
            name="ck_interview_type",
        ),
        CheckConstraint("mode IN ('practice','simulation')", name="ck_interview_mode"),
        CheckConstraint(
            "status IN ('created','planning','waiting_for_answer','evaluating','paused','completed','cancelled','failed')",
            name="ck_interview_status",
        ),
        CheckConstraint("question_limit BETWEEN 1 AND 30", name="ck_interview_question_limit"),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes BETWEEN 5 AND 120",
            name="ck_interview_duration",
        ),
        CheckConstraint(
            "revision >= 0 AND current_round >= 0 AND current_question >= 0",
            name="ck_interview_counters",
        ),
        Index("ix_interviews_candidate_created", "candidate_id", "created_at"),
    )


class InterviewPlan(Record, Base):
    __tablename__ = "interview_plans"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    objectives: Mapped[list] = mapped_column(JSONB)
    topics: Mapped[list] = mapped_column(JSONB)
    context_snapshot: Mapped[dict] = mapped_column(JSONB)
    prompt_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))


class InterviewRound(Record, Base):
    __tablename__ = "interview_rounds"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    topic: Mapped[str] = mapped_column(String(120))
    objective: Mapped[str] = mapped_column(Text)
    question_budget: Mapped[int] = mapped_column(Integer)
    initial_difficulty: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    __table_args__ = (
        UniqueConstraint("interview_id", "ordinal", name="uq_interview_round_ordinal"),
        CheckConstraint("ordinal > 0 AND question_budget > 0", name="ck_round_positive"),
        CheckConstraint("initial_difficulty BETWEEN 1 AND 5", name="ck_round_difficulty"),
        CheckConstraint("status IN ('pending','active','completed')", name="ck_round_status"),
    )


class InterviewQuestion(Record, Base):
    __tablename__ = "interview_questions"
    coding_problem_id: Mapped[UUID | None] = mapped_column(ForeignKey("coding_problems.id"))
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    round_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_rounds.id", ondelete="CASCADE"), index=True
    )
    parent_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="SET NULL")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(120))
    skill: Mapped[str | None] = mapped_column(String(120))
    difficulty: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="waiting")
    operation_id: Mapped[UUID] = mapped_column(unique=True)
    __table_args__ = (
        UniqueConstraint("interview_id", "sequence", name="uq_interview_question_sequence"),
        CheckConstraint("sequence > 0 AND difficulty BETWEEN 1 AND 5", name="ck_question_values"),
        CheckConstraint("state IN ('waiting','answered')", name="ck_question_state"),
    )


class InterviewAnswer(Record, Base):
    __tablename__ = "interview_answers"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), unique=True
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    idempotency_key: Mapped[UUID]
    payload_hash: Mapped[str] = mapped_column(String(64))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("interview_id", "idempotency_key", name="uq_answer_idempotency"),
        CheckConstraint("sequence > 0", name="ck_answer_sequence"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="ck_answer_duration"
        ),
        CheckConstraint("status IN ('submitted','evaluated')", name="ck_answer_status"),
    )


class AnswerEvaluation(Record, Base):
    __tablename__ = "answer_evaluations"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="CASCADE"), unique=True
    )
    correctness: Mapped[float] = mapped_column(Numeric(4, 3))
    relevance: Mapped[float] = mapped_column(Numeric(4, 3))
    completeness: Mapped[float] = mapped_column(Numeric(4, 3))
    technical_depth: Mapped[float] = mapped_column(Numeric(4, 3))
    reasoning: Mapped[float] = mapped_column(Numeric(4, 3))
    clarity: Mapped[float] = mapped_column(Numeric(4, 3))
    strengths: Mapped[list] = mapped_column(JSONB)
    weaknesses: Mapped[list] = mapped_column(JSONB)
    missing_concepts: Mapped[list] = mapped_column(JSONB)
    misconceptions: Mapped[list] = mapped_column(JSONB)
    evidence: Mapped[list] = mapped_column(JSONB)
    feedback: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    grounding_status: Mapped[str] = mapped_column(String(24), default="insufficient")
    evaluation_notes: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    __table_args__ = (
        CheckConstraint(
            "correctness BETWEEN 0 AND 1 AND relevance BETWEEN 0 AND 1 AND completeness BETWEEN 0 AND 1 AND technical_depth BETWEEN 0 AND 1 AND reasoning BETWEEN 0 AND 1 AND clarity BETWEEN 0 AND 1 AND confidence BETWEEN 0 AND 1",
            name="ck_evaluation_scales",
        ),
        CheckConstraint(
            "grounding_status IN ('grounded','insufficient')", name="ck_evaluation_grounding"
        ),
    )


class AdaptiveDecision(Record, Base):
    __tablename__ = "adaptive_decisions"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_evaluations.id", ondelete="CASCADE"), unique=True
    )
    action: Mapped[str] = mapped_column(String(32))
    target_topic: Mapped[str | None] = mapped_column(String(120))
    difficulty: Mapped[int] = mapped_column(Integer)
    reason_codes: Mapped[list] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint(
            "action IN ('ask_follow_up','increase_difficulty','maintain_difficulty','decrease_difficulty','revisit_topic','change_topic','test_missing_concept','end_interview')",
            name="ck_adaptive_action",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_decision_difficulty"),
    )


class InterviewJob(Record, Base):
    __tablename__ = "interview_jobs"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    expected_revision: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("kind IN ('plan','answer','stt','tts','coding','coding_validate')", name="ck_interview_job_kind"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_interview_job_status",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts BETWEEN 1 AND 5", name="ck_interview_job_attempts"
        ),
    )
