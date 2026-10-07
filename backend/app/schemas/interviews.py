from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.identity import Input

InterviewType = Literal["technical", "project", "behavioral", "mixed", "coding"]
InterviewMode = Literal["practice", "simulation"]
InterviewStatus = Literal[
    "created",
    "planning",
    "waiting_for_answer",
    "evaluating",
    "paused",
    "completed",
    "cancelled",
    "failed",
]
AdaptiveAction = Literal[
    "ask_follow_up",
    "increase_difficulty",
    "maintain_difficulty",
    "decrease_difficulty",
    "revisit_topic",
    "change_topic",
    "test_missing_concept",
    "end_interview",
]


class InterviewCreate(Input):
    vision_enabled: bool = True
    vision_phone_enabled: bool = True
    coding_problem_ids: list[UUID] = Field(default_factory=list, max_length=30)
    interview_type: InterviewType
    mode: InterviewMode
    job_id: UUID | None = None
    resume_id: UUID | None = None
    question_limit: int = Field(default=8, ge=1, le=30)
    duration_minutes: int | None = Field(default=None, ge=5, le=120)
    selected_topics: list[str] = Field(default_factory=list, max_length=12)
    difficulty: int = Field(default=2, ge=1, le=5)
    candidate_focus: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=1000)
    show_hints: bool = True
    use_memory: bool = True

    @field_validator("selected_topics")
    @classmethod
    def clean_topics(cls, value):
        cleaned = []
        for item in value:
            item = " ".join(item.split())
            if not 1 <= len(item) <= 80:
                raise ValueError("Each topic must be 1 to 80 characters")
            if item.casefold() not in {x.casefold() for x in cleaned}:
                cleaned.append(item)
        return cleaned

    @model_validator(mode="after")
    def project_context(self):
        if self.interview_type == "project" and self.resume_id is None:
            raise ValueError("Project interviews require a parsed resume")
        if self.mode == "simulation" and self.show_hints:
            self.show_hints = False
        return self


class StartInput(Input):
    expected_revision: int = Field(ge=0)


class AnswerInput(Input):
    voice_turn_id: UUID | None = None
    question_id: UUID
    text: str = Field(min_length=1, max_length=12000)
    duration_seconds: int | None = Field(default=None, ge=0, le=7200)
    expected_revision: int = Field(ge=0)
    idempotency_key: UUID

    @field_validator("text")
    @classmethod
    def clean_answer(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Answer cannot be blank")
        return value


class TransitionInput(Input):
    expected_revision: int = Field(ge=0)


class PlanTopic(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=500)
    question_budget: int = Field(ge=1, le=30)
    initial_difficulty: int = Field(ge=1, le=5)
    skill: str | None = Field(default=None, max_length=120)


class PlanResult(BaseModel):
    objectives: list[str] = Field(min_length=1, max_length=12)
    topics: list[PlanTopic] = Field(min_length=1, max_length=12)


class QuestionResult(BaseModel):
    question: str = Field(min_length=10, max_length=1500)
    topic: str = Field(min_length=1, max_length=120)
    skill: str | None = Field(default=None, max_length=120)
    difficulty: int = Field(ge=1, le=5)
    question_type: Literal["technical", "project", "behavioral", "situational", "follow_up"]
    reason: str = Field(min_length=1, max_length=500)


class EvaluationResult(BaseModel):
    correctness: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    technical_depth: float = Field(ge=0, le=1)
    reasoning: float = Field(ge=0, le=1)
    clarity: float = Field(ge=0, le=1)
    strengths: list[str] = Field(max_length=8)
    weaknesses: list[str] = Field(max_length=8)
    missing_concepts: list[str] = Field(max_length=8)
    misconceptions: list[str] = Field(max_length=8)
    evidence: list[str] = Field(max_length=8)
    feedback: str = Field(min_length=1, max_length=1500)
    hint: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)


class GroundedEvidence(BaseModel):
    knowledge_chunk_id: UUID
    claim: str = Field(min_length=1, max_length=500)
    relationship: Literal["supports", "contradicts", "insufficient"]


class GroundedEvaluationResult(EvaluationResult):
    knowledge_evidence: list[GroundedEvidence] = Field(max_length=12)
    evaluation_notes: str = Field(min_length=1, max_length=1500)
    grounding_status: Literal["grounded", "insufficient"]


class KnowledgeEvidenceOut(GroundedEvidence):
    document_id: UUID
    title: str
    source: str
    content: str
    retrieval_rank: int
    similarity: float


class EvaluationOut(EvaluationResult):
    id: UUID
    knowledge_evidence: list[KnowledgeEvidenceOut] = Field(default_factory=list)
    evaluation_notes: str = ""
    grounding_status: Literal["grounded", "insufficient"] = "insufficient"
    model_config = ConfigDict(from_attributes=True)


class DecisionOut(BaseModel):
    id: UUID
    action: AdaptiveAction
    target_topic: str | None
    difficulty: int
    reason_codes: list[str]
    explanation: str
    policy_version: str
    model_config = ConfigDict(from_attributes=True)


class QuestionOut(BaseModel):
    coding_problem_id: UUID | None = None
    id: UUID
    sequence: int
    text: str
    topic: str
    skill: str | None
    difficulty: int
    question_type: str
    state: str
    model_config = ConfigDict(from_attributes=True)


class AnswerOut(BaseModel):
    id: UUID
    question_id: UUID
    sequence: int
    text: str
    duration_seconds: int | None
    status: str
    submitted_at: datetime
    evaluation: EvaluationOut | None = None
    decision: DecisionOut | None = None
    model_config = ConfigDict(from_attributes=True)


class PlanOut(BaseModel):
    id: UUID
    objectives: list[str]
    topics: list[dict]
    model_config = ConfigDict(from_attributes=True)


class InterviewOut(BaseModel):
    id: UUID
    interview_type: InterviewType
    mode: InterviewMode
    status: InterviewStatus
    revision: int
    job_id: UUID | None
    resume_id: UUID | None
    question_limit: int
    duration_minutes: int | None
    configuration: dict
    current_round: int
    current_question: int
    progress: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current: QuestionOut | None = None
    plan: PlanOut | None = None
    practice_feedback: EvaluationOut | None = None
    practice_decision: DecisionOut | None = None
    summary: dict | None
    error: dict | None = None


class OperationOut(BaseModel):
    interview_id: UUID
    operation_id: UUID
    status: str
    revision: int


class ProviderStatus(BaseModel):
    configured: bool
    provider: str | None
    model: str | None
    message: str
