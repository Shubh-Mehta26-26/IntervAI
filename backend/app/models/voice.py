"""Voice is an input interface; scores remain in answer_evaluations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record

STATES = (
    "idle",
    "generating_response",
    "playing_response",
    "ai_speaking",
    "ready_for_candidate",
    "listening",
    "processing_audio",
    "transcribing",
    "evaluating",
    "error",
)


class VoiceSession(Record, Base):
    __tablename__ = "voice_sessions"
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), unique=True
    )
    state: Mapped[str] = mapped_column(String(32), default="idle")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE")
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("state IN " + str(STATES), name="ck_voice_state"),
        CheckConstraint("revision >= 0", name="ck_voice_revision"),
    )


class VoiceTurn(Record, Base):
    __tablename__ = "voice_turns"
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("voice_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE")
    )
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="CASCADE"), unique=True
    )
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_jobs.id", ondelete="CASCADE"), unique=True
    )
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    request_key: Mapped[UUID] = mapped_column(unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    audio_key: Mapped[str | None] = mapped_column(String(64))
    audio_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    transcript: Mapped[str | None] = mapped_column(Text)
    provider_metadata: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("kind IN ('stt','tts')", name="ck_voice_kind"),
        CheckConstraint(
            "status IN ('queued','processing','ready','submitted','failed','cancelled')",
            name="ck_voice_turn_status",
        ),
    )
