from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.identity import Input

Language = Literal["python", "cpp", "java"]


class TestCase(Input):
    input: str = Field(max_length=4096)
    expected: str = Field(max_length=4096)

    @field_validator("input", "expected")
    @classmethod
    def byte_limit(cls, value):
        if len(value.encode()) > 4096:
            raise ValueError("Test content exceeds byte limit")
        return value


class ProblemInput(Input):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=20, max_length=6000)
    difficulty: int = Field(ge=1, le=5)
    topic: str = Field(min_length=2, max_length=120)
    skills: list[str] = Field(min_length=1, max_length=8)
    constraints: list[str] = Field(min_length=1, max_length=8)
    input_format: str = Field(min_length=5, max_length=1000)
    output_format: str = Field(min_length=5, max_length=1000)
    examples: list[TestCase] = Field(min_length=1, max_length=5)
    starter_code: dict[Language, str]
    supported_languages: list[Language] = Field(min_length=1, max_length=3)
    public_tests: list[TestCase] = Field(min_length=1, max_length=5)
    hidden_tests: list[TestCase] = Field(min_length=1, max_length=15)
    time_ms: int = Field(default=1000, ge=100, le=3000)
    memory_mb: int = Field(default=128, ge=64, le=256)
    reference_solutions: dict[Language, str]

    @model_validator(mode="after")
    def complete_languages(self):
        if len(set(self.supported_languages)) != len(self.supported_languages):
            raise ValueError("Duplicate language")
        if set(self.starter_code) != set(self.supported_languages) or set(
            self.reference_solutions
        ) != set(self.supported_languages):
            raise ValueError("Each language requires starter code and a reference solution")
        if any(
            not 1 <= len(source.encode()) <= 32768
            for source in [*self.starter_code.values(), *self.reference_solutions.values()]
        ):
            raise ValueError("Source byte limit exceeded")
        if any(not 1 <= len(value) <= 240 for value in [*self.skills, *self.constraints]):
            raise ValueError("Invalid skill or constraint")
        return self


class GenerationInput(Input):
    interview_id: UUID
    topic: str = Field(min_length=2, max_length=120)
    difficulty: int = Field(ge=1, le=5)


class ExecutionInput(Input):
    question_id: UUID
    expected_revision: int = Field(ge=0)
    idempotency_key: UUID
    language: Language
    source_code: str = Field(min_length=1, max_length=32768)
    explanation: str = Field(default="", max_length=4000)

    @field_validator("source_code")
    @classmethod
    def source_bytes(cls, value):
        if not 1 <= len(value.encode()) <= 32768:
            raise ValueError("Source exceeds 32768 bytes")
        return value


class ComplexityAnalysis(Input):
    time_complexity: str = Field(min_length=1, max_length=200)
    space_complexity: str = Field(min_length=1, max_length=200)
    reasoning: str = Field(min_length=1, max_length=2000)
    code_quality: str = Field(min_length=1, max_length=1500)
    edge_cases: str = Field(min_length=1, max_length=1500)


ExecutionState = Literal[
    "COMPLETED",
    "COMPILE_ERROR",
    "RUNTIME_ERROR",
    "TIMEOUT",
    "MEMORY_LIMIT",
    "OUTPUT_LIMIT",
    "SYSTEM_ERROR",
    "CANCELLED",
]


class ExecutionCase(Input):
    status: ExecutionState
    passed: bool = Field(strict=True)
    stdout: str = Field(max_length=32768)
    stderr: str = Field(max_length=32768)
    execution_time_ms: int | None = Field(default=None, strict=True, ge=0, le=100000)
    memory_kb: int | None = Field(default=None, strict=True, ge=0, le=1048576)


class ExecutionResult(Input):
    status: ExecutionState
    tests_total: int = Field(strict=True, ge=1, le=20)
    tests_passed: int = Field(strict=True, ge=0, le=20)
    execution_time_ms: int | None = Field(default=None, strict=True, ge=0, le=100000)
    memory_kb: int | None = Field(default=None, strict=True, ge=0, le=1048576)
    cases: list[ExecutionCase] = Field(default_factory=list, max_length=20)
    stdout: str | None = Field(default=None, max_length=32768)
    stderr: str | None = Field(default=None, max_length=32768)

    @model_validator(mode="after")
    def consistent(self):
        if self.tests_passed > self.tests_total or len(self.cases) > self.tests_total:
            raise ValueError("Invalid test counts")
        if self.status == "COMPLETED" and (
            len(self.cases) != self.tests_total
            or sum(case.passed for case in self.cases) != self.tests_passed
            or any(case.status != "COMPLETED" for case in self.cases)
        ):
            raise ValueError("Completed execution must contain a consistent result for every test")
        return self
