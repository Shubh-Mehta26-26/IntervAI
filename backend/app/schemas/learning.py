from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.identity import Input


class PlanInput(Input):
    gap_ids: list[UUID] = Field(default_factory=list, max_length=6)
    topics: list[str] = Field(default_factory=list, max_length=4)
    job_id: UUID | None = None
    idempotency_key: UUID
    regenerate: bool = False

    @model_validator(mode="after")
    def selected_focus(self):
        if not self.gap_ids and not self.topics and not self.job_id:
            raise ValueError("Choose learning topics, a target job, or confirmed knowledge gaps.")
        if self.gap_ids and self.topics:
            raise ValueError("Create either a topic plan or a confirmed-gap plan.")
        return self


class RevisionInput(Input):
    expected_revision: int = Field(ge=0)


class PracticeInput(Input):
    idempotency_key: UUID


class SelfCheckInput(RevisionInput):
    selected_index: int = Field(ge=0, le=5)


class RetryInput(Input):
    idempotency_key: UUID
    mode: Literal["single", "multiple", "topic", "skill", "recommended"] = "recommended"
    gap_ids: list[UUID] = Field(default_factory=list, max_length=6)
    subject: str | None = Field(default=None, min_length=1, max_length=120)
    plan_id: UUID | None = None
    job_id: UUID | None = None
    question_limit: int = Field(default=6, ge=1, le=30)


class LearningContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1, max_length=6000)
    examples: list[str] = Field(max_length=5)
    practice_question: str = Field(min_length=10, max_length=1500)
    hints: list[str] = Field(max_length=4)
    source_chunk_ids: list[UUID] = Field(max_length=8)

    @field_validator("examples", "hints")
    @classmethod
    def bounded_text(cls, values):
        if any(not value.strip() or len(value) > 1500 for value in values):
            raise ValueError("Content entries must be nonempty and at most 1500 characters")
        return values
