"""Deterministic HTTP/queue/engine tests. Execution values are test-only mock fixtures.
Real execution and attack assertions live in sandbox/verify.py, inside the runner.
"""

import asyncio
import json
from uuid import uuid4

import httpx
import psycopg
import pytest
from app.main import app
from app.schemas.coding import ComplexityAnalysis, ExecutionResult, ProblemInput
from app.schemas.coding import TestCase as CodingCase
from app.services.coding import safe_result
from app.services.coding_catalog import definitions
from app.worker import process_interview_one
from conftest import ORIGIN, Harness, run
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_interviews import (
    FakeEmbeddingProvider,
    FakeProvider,
    create_interview,
    mutate,
    signed_in,
)


class CodingLLM(FakeProvider):
    async def structured(self, *, system, user, schema, name):
        if schema is ComplexityAnalysis:
            self.calls.append((name, user))
            return ComplexityAnalysis(
                time_complexity="O(n)",
                space_complexity="O(1)",
                reasoning="Test-only fixture estimate for a linear accumulation.",
                code_quality="Test-only qualitative review.",
                edge_cases="Consider empty input.",
            )
        return await super().structured(system=system, user=user, schema=schema, name=name)


class MockRunner:
    """Never executes candidate source. Only a deliberately named test double."""

    def __init__(self, status="COMPLETED", passed=None):
        self.status, self.passed, self.calls = status, passed, []
        self.cancelled = []

    async def execute(self, payload):
        self.calls.append(payload)
        total = len(payload["tests"])
        passed = total if self.passed is None else min(total, self.passed)
        return {
            "status": self.status,
            "tests_total": total,
            "tests_passed": passed if self.status == "COMPLETED" else 0,
            "execution_time_ms": 17,
            "memory_kb": 2048,
            "stderr": "test-only compile diagnostic",
            "cases": [
                {
                    "status": self.status,
                    "passed": i < passed,
                    "stdout": "MOCK_HIDDEN_STDIN",
                    "stderr": "MOCK_HIDDEN_DIAGNOSTIC",
                    "execution_time_ms": 17,
                    "memory_kb": 2048,
                }
                for i in range(total)
            ],
        }

    async def cancel(self, identifier):
        self.cancelled.append(identifier)


def work(identity, runner=None, provider=None):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def execute():
        try:
            return await process_interview_one(
                factory,
                provider or CodingLLM(),
                FakeEmbeddingProvider(),
                execution=runner or MockRunner(),
            )
        finally:
            await engine.dispose()

    return run(execute())


def active(identity, limit=2, register=True):
    if register:
        signed_in(identity)
    row = create_interview(
        identity, interview_type="coding", question_limit=limit, selected_topics=["Arrays"]
    ).json()
    assert "id" in row, row
    # Catalog validation is durable worker work, not an API subprocess.
    while identity.sql(
        "SELECT id FROM interview_jobs WHERE kind='coding_validate' AND status='queued'"
    ):
        assert work(identity)
    response = mutate(
        identity, "POST", f"/interviews/{row['id']}/start", {"expected_revision": row["revision"]}
    )
    assert response.status_code == 202, response.text
    assert work(identity)
    row = identity.request("GET", f"/interviews/{row['id']}").json()
    assert row["status"] == "waiting_for_answer", row
    assert row["current"]["coding_problem_id"]
    return row


def execution(identity, row, mode="run", **changes):
    body = {
        "question_id": row["current"]["id"],
        "expected_revision": row["revision"],
        "idempotency_key": str(uuid4()),
        "language": "python",
        "source_code": "print('test-only fixture')",
        "explanation": "A test-only fixture explanation.",
        **changes,
    }
    return mutate(identity, "POST", f"/interviews/{row['id']}/coding/{mode}", body)


def test_problem_schemas_and_catalog():
    assert len(list(definitions())) >= 3
    for _, problem in definitions():
        assert set(problem.reference_solutions) == {"python", "cpp", "java"}
        assert problem.public_tests and problem.hidden_tests
    with pytest.raises(ValidationError):
        CodingCase(input="🙂" * 2000, expected="x")
    _, problem = next(definitions())
    with pytest.raises(ValidationError):
        ProblemInput.model_validate({**problem.model_dump(), "time_ms": 999999})
    with pytest.raises(ValidationError):
        ProblemInput.model_validate({**problem.model_dump(), "reference_solutions": {}})


def test_authenticated_owned_problems_and_validation(identity):
    assert identity.request("GET", "/coding/problems").status_code == 401
    signed_in(identity)
    _, schema = next(definitions())
    response = mutate(identity, "POST", "/coding/problems", schema.model_dump())
    assert response.status_code == 201, response.text
    problem = response.json()
    assert problem["validation_status"] == "draft"
    assert "reference_solutions" not in response.text and "hidden_tests" not in response.text
    interview = create_interview(identity).json()
    assert (
        mutate(
            identity,
            "POST",
            f"/coding/problems/{problem['id']}/validate",
            {"interview_id": interview["id"], "topic": "Arrays", "difficulty": 1},
        ).status_code
        == 200
    )
    assert work(identity)
    assert (
        identity.request("GET", f"/coding/problems/{problem['id']}").json()["validation_status"]
        == "validated"
    )
    other = Harness(identity.url)
    assert other.register("other-coding@example.com").status_code == 201
    assert other.login("other-coding@example.com").status_code == 200
    assert other.request("GET", f"/coding/problems/{problem['id']}").status_code == 404


def test_bad_reference_is_rejected(identity):
    signed_in(identity)
    _, schema = next(definitions())
    problem = mutate(identity, "POST", "/coding/problems", schema.model_dump()).json()
    interview = create_interview(identity).json()
    mutate(
        identity,
        "POST",
        f"/coding/problems/{problem['id']}/validate",
        {"interview_id": interview["id"], "topic": "Arrays", "difficulty": 1},
    )
    work(identity, MockRunner(passed=0))
    assert (
        identity.request("GET", f"/coding/problems/{problem['id']}").json()["validation_status"]
        == "rejected"
    )


def test_run_duplicate_retry_conflict_and_history(identity):
    row = active(identity)
    key = str(uuid4())
    first = execution(identity, row, idempotency_key=key)
    assert first.status_code == 202, first.text
    assert execution(identity, row, idempotency_key=key).json()["id"] == first.json()["id"]
    assert execution(identity, row).json()["id"] == first.json()["id"]
    assert execution(identity, row, idempotency_key=key, source_code="other").status_code == 409
    assert execution(identity, row, source_code="other").status_code == 409
    runner = MockRunner()
    assert work(identity, runner)
    assert len(runner.calls) == 1 and len(runner.calls[0]["tests"]) == 2
    saved = identity.request("GET", f"/coding/submissions/{first.json()['id']}").json()
    assert saved["status"] == "ACCEPTED" and saved["result"]["cases"]
    assert execution(identity, row, idempotency_key=key).json()["id"] == saved["id"]
    assert len(identity.request("GET", f"/interviews/{row['id']}/coding/submissions").json()) == 1
    with pytest.raises(psycopg.Error):
        identity.sql(
            "UPDATE coding_submissions SET source_code='replacement' WHERE id=%s", (saved["id"],)
        )


@pytest.mark.parametrize(
    "status",
    ["COMPILE_ERROR", "RUNTIME_ERROR", "TIMEOUT", "MEMORY_LIMIT", "OUTPUT_LIMIT", "SYSTEM_ERROR"],
)
def test_execution_states_are_persisted_without_hidden_output(identity, status):
    row = active(identity, limit=1)
    response = execution(identity, row, "submit")
    assert response.status_code == 202, response.text
    assert work(identity, MockRunner(status))
    saved = identity.request("GET", f"/coding/submissions/{response.json()['id']}")
    assert saved.json()["execution_status"] == status
    assert "MOCK_HIDDEN" not in saved.text and '"cases"' not in saved.text
    if status == "SYSTEM_ERROR":
        assert saved.json()["answer_id"] is None
        assert (
            identity.request("GET", f"/interviews/{row['id']}").json()["status"]
            == "waiting_for_answer"
        )


@pytest.mark.parametrize("passed,status", [(0, "WRONG_ANSWER"), (1, "PARTIAL"), (4, "ACCEPTED")])
def test_authoritative_correctness_adaptive_memory_pipeline(identity, passed, status):
    row = active(identity)
    response = execution(identity, row, "submit")
    assert response.status_code == 202
    runner = MockRunner(passed=passed)
    work(identity, runner)
    saved = identity.request("GET", f"/coding/submissions/{response.json()['id']}").json()
    assert saved["status"] == status and saved["answer_id"]
    assert len(runner.calls[0]["tests"]) == 4
    provider = CodingLLM()
    assert work(identity, provider=provider)
    evaluations = identity.sql(
        "SELECT correctness,feedback FROM answer_evaluations WHERE answer_id=%s",
        (saved["answer_id"],),
    )
    assert (
        float(evaluations[0]["correctness"]) == passed / 4
    )  # LLM fixture always incorrectly proposes .9!
    assert f"{passed}/4 tests passed" in evaluations[0]["feedback"]
    details = identity.request("GET", f"/interviews/{row['id']}").json()
    assert details["status"] == "waiting_for_answer" and details["current"]["coding_problem_id"]
    assert details["current"]["id"] != row["current"]["id"]
    evidence = identity.sql(
        "SELECT correctness,grounded FROM memory_evidence WHERE interview_id=%s", (row["id"],)
    )
    assert evidence and all(
        float(e["correctness"]) == passed / 4 and e["grounded"] for e in evidence
    )
    analysis = identity.request("GET", f"/coding/submissions/{saved['id']}").json()["analysis"]
    assert analysis["kind"] == "LLM-estimated complexity"
    prompt = next(user for name, user in provider.calls if name == "answer_evaluation")
    assert '"tests_passed":' in prompt and "source_code" in prompt and "MOCK_HIDDEN" not in prompt


def test_cancel_stale_cross_user_and_text_bypass(identity):
    row = active(identity)
    first = execution(identity, row).json()
    assert (
        mutate(identity, "POST", f"/coding/submissions/{first['id']}/cancel", {}).json()[
            "execution_status"
        ]
        == "CANCELLED"
    )
    assert not work(identity)
    assert execution(identity, row, expected_revision=row["revision"] + 1).status_code == 409
    assert execution(identity, row, source_code="🙂" * 10000).status_code == 422
    second = execution(identity, row).json()
    mutate(
        identity, "POST", f"/interviews/{row['id']}/pause", {"expected_revision": row["revision"]}
    )
    runner = MockRunner()
    work(identity, runner)
    assert not runner.calls
    assert (
        identity.request("GET", f"/coding/submissions/{second['id']}").json()["execution_status"]
        == "CANCELLED"
    )
    other = Harness(identity.url)
    other.register("other-coding@example.com")
    other.login("other-coding@example.com")
    assert other.request("GET", f"/coding/submissions/{second['id']}").status_code == 404
    assert (
        mutate(other, "POST", f"/coding/submissions/{second['id']}/cancel", {}).status_code == 404
    )
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{row['id']}/answers",
            {
                "question_id": row["current"]["id"],
                "text": "bypass",
                "expected_revision": row["revision"],
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 409
    )


def test_no_hidden_output_even_when_program_echoes_input():
    mocked = MockRunner()
    result = run(
        mocked.execute({"tests": [{"input": "SECRET_INPUT", "expected": "SECRET_EXPECTED"}]})
    )
    result["cases"][0]["stdout"] = "SECRET_INPUT SECRET_EXPECTED"
    assert "SECRET" not in json.dumps(safe_result(result, "submit"))
    assert "SECRET" in json.dumps(safe_result(result, "run"))


def test_coding_gap_learning_plan_and_fresh_retry(identity):
    signed_in(identity)
    titles = set()
    for _ in range(3):
        row = active(identity, limit=1, register=False)
        titles.add(row["current"]["text"])
        response = execution(identity, row, "submit")
        assert response.status_code == 202
        work(identity, MockRunner(passed=0))
        work(identity)
        assert identity.request("GET", f"/interviews/{row['id']}").json()["status"] == "completed"
    gaps = identity.request("GET", "/candidates/me/knowledge-gaps").json()
    confirmed = next(g for g in gaps if g["status"] == "confirmed" and g["topic"] == "Arrays")
    plan = mutate(
        identity,
        "POST",
        "/learning/plans",
        {"gap_ids": [confirmed["id"]], "idempotency_key": str(uuid4())},
    )
    assert plan.status_code == 201, plan.text
    retry = mutate(
        identity,
        "POST",
        "/learning/retries",
        {
            "gap_ids": [confirmed["id"]],
            "plan_id": plan.json()["id"],
            "question_limit": 1,
            "idempotency_key": str(uuid4()),
        },
    )
    assert retry.status_code == 201, retry.text
    retry_id = retry.json()["interview_id"]
    draft = identity.request("GET", f"/interviews/{retry_id}").json()
    assert draft["interview_type"] == "coding"
    started = mutate(
        identity, "POST", f"/interviews/{retry_id}/start", {"expected_revision": draft["revision"]}
    )
    assert started.status_code == 202, started.text
    work(identity)
    current = identity.request("GET", f"/interviews/{retry_id}").json()
    assert current["status"] == "waiting_for_answer", current
    assert current["current"]["text"] not in titles


def test_exhausted_coding_lease_finishes_execution_without_failing_interview(identity):
    row = active(identity)
    submission = execution(identity, row).json()
    identity.sql(
        "UPDATE interview_jobs SET attempts=3 WHERE id=(SELECT job_id FROM coding_submissions WHERE id=%s)",
        (submission["id"],),
    )
    work(identity)
    saved = identity.request("GET", f"/coding/submissions/{submission['id']}").json()
    assert saved["execution_status"] == "SYSTEM_ERROR"
    assert (
        identity.request("GET", f"/interviews/{row['id']}").json()["status"] == "waiting_for_answer"
    )


def test_generated_problem_is_private_and_requires_reference_validation(identity, monkeypatch):
    from app.api import coding as api_coding
    from app.api import interviews as api_interviews

    signed_in(identity)
    interview = create_interview(identity).json()
    _, generated = next(definitions())

    class Generator:
        name, model = "test-only", "generation-fixture"

        async def structured(self, **kwargs):
            assert kwargs["schema"] is ProblemInput
            assert "Arrays" in kwargs["user"] and "candidate" in kwargs["user"]
            return generated

    monkeypatch.setattr(api_coding, "get_provider", Generator)
    monkeypatch.setattr(api_interviews, "require_llm_ready", lambda: None)
    response = mutate(
        identity,
        "POST",
        "/coding/problems/generate",
        {"interview_id": interview["id"], "topic": "Arrays", "difficulty": 1},
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert (
        row["validation_status"] == "validating" and row["provenance"]["source"] == "ai-generated"
    )
    assert "hidden_tests" not in response.text and "reference_solutions" not in response.text
    work(identity)
    assert (
        identity.request("GET", f"/coding/problems/{row['id']}").json()["validation_status"]
        == "validated"
    )


def test_runner_contract_rejects_inconsistent_counts_and_fake_metrics():
    result = run(MockRunner().execute({"tests": [{"input": "", "expected": ""}]}))
    assert ExecutionResult.model_validate(result).tests_passed == 1
    for changes in (
        {"tests_passed": 2},
        {"execution_time_ms": -1},
        {"memory_kb": "fabricated"},
        {"cases": []},
    ):
        with pytest.raises(ValidationError):
            ExecutionResult.model_validate({**result, **changes})


def test_concurrent_submit_requests_share_one_submission_and_job(identity):
    row = active(identity)
    body = {
        "question_id": row["current"]["id"],
        "expected_revision": row["revision"],
        "idempotency_key": str(uuid4()),
        "language": "python",
        "source_code": "print('test fixture')",
    }

    async def race():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://test",
            cookies=identity.cookies,
            headers={"Origin": ORIGIN, "X-CSRF-Token": identity.csrf},
        ) as client:
            return await asyncio.gather(
                *[
                    client.post(f"/api/v1/interviews/{row['id']}/coding/submit", json=body)
                    for _ in range(2)
                ]
            )

    responses = run(race())
    assert all(r.status_code == 202 for r in responses), [r.text for r in responses]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert (
        len(identity.sql("SELECT id FROM coding_submissions WHERE interview_id=%s", (row["id"],)))
        == 1
    )
    assert (
        len(
            identity.sql(
                "SELECT id FROM interview_jobs WHERE interview_id=%s AND kind='coding'",
                (row["id"],),
            )
        )
        == 1
    )
