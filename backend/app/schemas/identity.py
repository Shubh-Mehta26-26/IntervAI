from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterInput(LoginInput):
    display_name: Name
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Password must not be blank")
        return value


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: Literal["candidate", "recruiter", "admin"]
    is_active: bool
    created_at: datetime


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: datetime


class GoalInput(Input):
    role_title: Name
    priority: int = Field(default=0, ge=0, le=20)
    active: bool = True


class DatedInput(Input):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        return self


class EducationInput(DatedInput):
    institution: ShortText
    qualification: ShortText
    field_of_study: str | None = Field(default=None, max_length=160)


class ExperienceInput(DatedInput):
    organization: ShortText
    title: ShortText
    description: str | None = Field(default=None, max_length=2000)


class PreferencesInput(Input):
    interview_mode: Literal["text", "voice"] = "text"
    interview_duration_minutes: Literal[10, 20, 30, 45, 60] = 20
    locale: Literal["en", "hi", "en-IN"] = "en"


class ProfilePatch(Input):
    expected_revision: int = Field(ge=0)
    display_name: Name | None = None
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[+0-9() .-]*$")
    location: str | None = Field(default=None, max_length=160)
    headline: str | None = Field(default=None, max_length=200)
    biography: str | None = Field(default=None, max_length=3000)
    timezone: str | None = Field(default=None, max_length=64)
    experience_months: int | None = Field(default=None, ge=0, le=720)
    career_interests: (
        list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]]
        | None
    ) = Field(default=None, max_length=12)
    goals: list[GoalInput] | None = Field(default=None, max_length=10)
    education: list[EducationInput] | None = Field(default=None, max_length=20)
    experience: list[ExperienceInput] | None = Field(default=None, max_length=20)
    preferences: PreferencesInput | None = None

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Use a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def collections_and_nulls(self):
        for field in (
            "display_name",
            "timezone",
            "experience_months",
            "career_interests",
            "goals",
            "education",
            "experience",
            "preferences",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.goals is not None:
            titles = [g.role_title.lower() for g in self.goals]
            if len(titles) != len(set(titles)):
                raise ValueError("Target roles must be unique")
        if self.career_interests is not None and len(set(self.career_interests)) != len(
            self.career_interests
        ):
            raise ValueError("Career interests must be unique")
        return self


class ProfileOut(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    email: str
    phone: str | None
    location: str | None
    headline: str | None
    biography: str | None
    timezone: str
    experience_months: int
    revision: int
    career_interests: list[str]
    goals: list[GoalInput]
    education: list[EducationInput]
    experience: list[ExperienceInput]
    preferences: PreferencesInput
    created_at: datetime
    updated_at: datetime
