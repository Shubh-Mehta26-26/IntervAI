from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.identity import Input, Name, ShortText


class RecruiterJobInput(Input):
    title: Name
    company: ShortText
    description: str = Field(min_length=40, max_length=16000)


class RecruiterJobPatch(Input):
    expected_version: int = Field(ge=1)
    title: Name | None = None
    company: ShortText | None = None
    description: str | None = Field(default=None, min_length=40, max_length=16000)
    status: Literal["active", "paused", "closed"] | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not any(key != "expected_version" for key in self.model_fields_set):
            raise ValueError("Provide at least one job change.")
        return self


class ApplicationInput(Input):
    recruiter_job_id: UUID
    candidate_job_id: UUID
    share_consent: Literal[True]


class ApplicationStatusInput(Input):
    status: Literal["withdrawn", "closed"]


class AdminRoleInput(Input):
    role: Literal["candidate", "recruiter", "admin"]


class ReportListItem(Input):
    id: UUID
    interview_id: UUID
    version: int
    generated_at: datetime
    interview_type: str
    job_title: str | None
