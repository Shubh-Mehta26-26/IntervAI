from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.identity import Input


class Evidence(BaseModel):
    source: str
    quote: str = Field(max_length=2000)
    line: int = Field(ge=1)
    section: str
    kind: Literal["applied", "mentioned"] = "mentioned"


class ExtractedSkill(BaseModel):
    slug: str
    name: str
    category: str
    evidence: list[Evidence]


class ResumeFacts(BaseModel):
    schema_version: int = 1
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    education: list[Evidence] = Field(default_factory=list)
    experience: list[Evidence] = Field(default_factory=list)
    projects: list[Evidence] = Field(default_factory=list)
    certifications: list[Evidence] = Field(default_factory=list)
    achievements: list[Evidence] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    original_name: str
    media_type: str
    size_bytes: int
    version: int
    status: str
    parsing_status: str
    error: str | None
    extracted_text: str | None
    parsed_data: ResumeFacts | None
    parser_version: str | None
    created_at: datetime


class JobInput(Input):
    title: str = Field(min_length=1, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    description: str = Field(min_length=30, max_length=30000)

    @field_validator("title", "company", "description", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description")
    @classmethod
    def bounded_lines(cls, value):
        if any(len(line) > 2000 for line in value.splitlines()):
            raise ValueError("Add line breaks; each paragraph must be at most 2000 characters")
        return value


class JobPatch(JobInput):
    expected_version: int = Field(ge=1)


class Requirement(ExtractedSkill):
    requirement: Literal["required", "preferred", "unspecified"]


class JobAnalysis(BaseModel):
    schema_version: int = 1
    parser_version: str
    skills: list[Requirement]
    responsibilities: list[Evidence]
    qualifications: list[Evidence]
    experience_requirements: list[Evidence]
    other_requirements: list[Evidence]
    domain: str | None = None
    warnings: list[str]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    company: str | None
    description: str
    source: str
    version: int
    status: str
    analysis: JobAnalysis | None
    created_at: datetime
    updated_at: datetime


class MatchInput(Input):
    resume_id: UUID | None = None


class MatchSkill(BaseModel):
    skill_id: UUID
    name: str
    category: str
    requirement: str
    status: Literal["demonstrated", "partial", "not_demonstrated"]
    explanation: str
    evidence: list[Evidence]
    job_evidence: list[Evidence]


class MatchResult(BaseModel):
    policy_version: str
    job_version: int
    profile_revision: int
    skills: list[MatchSkill]
    unassessed_requirements: list[Evidence]
    explanation: str


class MatchOut(BaseModel):
    id: UUID
    resume_id: UUID | None
    created_at: datetime
    stale: bool
    result: MatchResult
