from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.identity import Input


class CareerProfileInput(Input):
    expected_revision: int = Field(ge=0)
    expected_candidate_revision: int = Field(ge=0)
    target_roles: list[str] = Field(max_length=8)
    career_interests: list[str] = Field(max_length=12)
    preferred_domains: list[str] = Field(max_length=8)
    geographic_preferences: list[str] = Field(max_length=8)
    industry_preferences: list[str] = Field(max_length=8)
    role_preferences: list[str] = Field(max_length=8)
    dismissed_roles: list[str] = Field(default_factory=list, max_length=12)

    @field_validator(
        "target_roles",
        "career_interests",
        "preferred_domains",
        "geographic_preferences",
        "industry_preferences",
        "role_preferences",
        "dismissed_roles",
    )
    @classmethod
    def bounded_entries(cls, values):
        if any(not value.strip() or len(value.strip()) > 80 for value in values):
            raise ValueError("Use nonempty entries of at most 80 characters.")
        return list(dict.fromkeys(value.strip() for value in values))


class CareerAnalyze(Input):
    expected_revision: int = Field(ge=0)
    idempotency_key: UUID
    role_ids: list[str] = Field(default_factory=list, max_length=8)
    job_id: UUID | None = None


class CareerRoadmap(Input):
    analysis_id: UUID
    role_id: str = Field(max_length=80)
    gap_ids: list[UUID] = Field(min_length=1, max_length=6)
    idempotency_key: UUID


class CareerChoiceInput(Input):
    analysis_id: UUID
    role_id: str = Field(max_length=80)
    skill: str = Field(max_length=120)
    state: Literal["pursue", "dismissed"]
    expected_revision: int = Field(ge=0)


class AdviceInput(Input):
    use_rag: bool = True


class AdviceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: str = Field(max_length=80)
    skill: str = Field(max_length=120)
    status: Literal["DEMONSTRATED", "DEVELOPING", "LIMITED_EVIDENCE", "NOT_DEMONSTRATED"]
    explanation: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(max_length=8)


class AdvisorContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[AdviceObservation] = Field(max_length=12)
    reflective_questions: list[str] = Field(min_length=1, max_length=5)
    source_chunk_ids: list[UUID] = Field(max_length=8)
    grounding_status: Literal["grounded", "insufficient"]

    @field_validator("reflective_questions")
    @classmethod
    def questions(cls, values):
        if any(not value.strip() or len(value) > 800 for value in values):
            raise ValueError("Reflection questions must be bounded and nonempty.")
        return values
