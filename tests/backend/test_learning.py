import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.models.learning import LearningItem, LearningPlan
from app.schemas.learning import LearningContent, PlanInput, RetryInput
from app.services import learning
from app.services.memory import CandidateMemoryService
from conftest import Harness, run
from sqlalchemy import select
from test_interviews import FakeEmbeddingProvider, mutate, worker
from test_memory import MemoryJourneyProvider, database, make_evaluation, observation, setup


def confirmed(identity):
    owner, chunk = setup(identity)
    engine, sessions = database(identity)

    async def seed():
        async with sessions() as db:
            for _ in range(3):
                _, _, evaluation = await make_evaluation(db, owner, chunk)
                await CandidateMemoryService.update(db, evaluation)
                await db.commit()
        await engine.dispose()

    run(seed())
    gaps = identity.request("GET", "/candidates/me/knowledge-gaps").json()
    return owner, next(
        x for x in gaps if x["kind"] == "concept" and x["subject"] == "normalization"
    )


def plan(identity, gap_id, **fields):
    return mutate(
        identity,
        "POST",
        "/learning/plans",
        {"gap_ids": [gap_id], "idempotency_key": str(uuid4()), **fields},
    )


def test_priority_deterministic_evidence_and_job_relevance():
    gap = SimpleNamespace(weakness_index=0.7, weak_interview_count=3)
    memory = SimpleNamespace(
        subject="normalization", topic="DBMS", evidence_strength=0.9, mean_correctness=0.3
    )
    base, reasons = learning.priority(gap, memory)
    targeted, extra = learning.priority(gap, memory, "Job requires normalization", "normalization")
    assert targeted - base == 20
    assert learning.priority(gap, memory) == (base, reasons)
    assert len(extra) == len(reasons) + 2


def test_plan_persistence_order_duplicates_progress_and_learning_action(identity):
    _, gap = confirmed(identity)
    key = str(uuid4())
    response = plan(identity, gap["id"], idempotency_key=key)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert [x["title"] for x in saved["items"]][:2] == ["Functional dependencies", "Candidate keys"]
    assert saved["progress"] == {"completed": 0, "total": 7}
    assert saved["targets"][0]["baseline"]["count"] == 3
    assert len(saved["targets"][0]["baseline"]["evidence_ids"]) == 3
    assert saved["items"][0]["content"]["grounding_status"] == "insufficient"
    assert plan(identity, gap["id"], idempotency_key=key).json()["id"] == saved["id"]
    assert plan(identity, gap["id"]).json()["id"] == saved["id"]
    assert plan(identity, gap["id"], idempotency_key=key, regenerate=True).status_code == 409
    start = mutate(
        identity, "POST", f"/learning/plans/{saved['id']}/start", {"expected_revision": 0}
    )
    assert start.status_code == 200
    assert (
        identity.request("GET", f"/candidates/me/knowledge-gaps/{gap['id']}").json()["status"]
        == "learning"
    )
    assert (
        len(
            identity.request("GET", f"/candidates/me/knowledge-gaps/{gap['id']}").json()[
                "learning_actions"
            ]
        )
        == 1
    )
    assert (
        mutate(
            identity, "POST", f"/learning/plans/{saved['id']}/start", {"expected_revision": 0}
        ).status_code
        == 200
    )
    stale = mutate(
        identity,
        "POST",
        f"/learning/items/{saved['items'][0]['id']}/complete",
        {"expected_revision": 0},
    )
    assert stale.status_code == 409
    current = start.json()
    for item in saved["items"]:
        completed = mutate(
            identity,
            "POST",
            f"/learning/items/{item['id']}/complete",
            {"expected_revision": current["revision"]},
        )
        assert completed.status_code == 200
        current = completed.json()
    assert current["status"] == "completed" and current["progress"]["completed"] == 7
    assert (
        identity.request("GET", "/candidates/me/knowledge-gaps").json()[0]["status"] != "resolved"
    )
    progress = identity.request("GET", "/candidates/me/progress").json()
    assert progress["plans"][0]["progress"]["completed"] == 7
    assert progress["recommendations"]
    assert plan(identity, gap["id"], regenerate=True).json()["id"] != saved["id"]


def test_practice_uses_existing_evaluator_without_mastery_credit(identity):
    owner, gap = confirmed(identity)
    saved = plan(identity, gap["id"]).json()
    item_id = saved["items"][0]["id"]
    key = str(uuid4())
    attempt = mutate(
        identity, "POST", f"/learning/items/{item_id}/practice", {"idempotency_key": key}
    ).json()
    assert (
        mutate(
            identity, "POST", f"/learning/items/{item_id}/practice", {"idempotency_key": key}
        ).json()["id"]
        == attempt["id"]
    )
    assert (
        mutate(
            identity,
            "POST",
            f"/learning/items/{item_id}/practice",
            {"idempotency_key": str(uuid4())},
        ).json()["id"]
        == attempt["id"]
    )
    state = identity.request("GET", f"/interviews/{attempt['interview_id']}").json()
    assert "Functional dependencies" in state["current"]["text"]
    count = identity.sql(
        "select count(*) as n from memory_evidence where candidate_id=%s", (owner,)
    )[0]["n"]
    payload = {
        "question_id": state["current"]["id"],
        "text": "Functional dependencies define relationships between attributes.",
        "expected_revision": state["revision"],
        "idempotency_key": str(uuid4()),
    }
    path = f"/learning/items/{item_id}/practice/{attempt['id']}/submit"
    submission = mutate(identity, "POST", path, payload)
    assert submission.status_code == 202, submission.text
    assert (
        mutate(identity, "POST", path, payload).json()["operation_id"]
        == submission.json()["operation_id"]
    )
    assert worker(identity, MemoryJourneyProvider(0.9))
    feedback = identity.request("GET", f"/interviews/{attempt['interview_id']}").json()
    assert feedback["status"] == "completed"
    assert feedback["practice_feedback"]["correctness"] == 0.9
    assert feedback["practice_feedback"]["knowledge_evidence"]
    assert (
        identity.sql("select count(*) as n from memory_evidence where candidate_id=%s", (owner,))[
            0
        ]["n"]
        == count
    )
    second = mutate(
        identity, "POST", f"/learning/items/{item_id}/practice", {"idempotency_key": str(uuid4())}
    ).json()
    assert second["id"] != attempt["id"]


def finish_retry(identity, attempt, score, limit):
    state = identity.request("GET", f"/interviews/{attempt['interview_id']}").json()
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{state['id']}/start",
            {"expected_revision": state["revision"]},
        ).status_code
        == 202
    )
    provider = MemoryJourneyProvider(score)
    provider.questions = int(attempt["id"].replace("-", "")[:4], 16)
    assert worker(identity, provider)
    assert provider.planning_context["retry_targets"][0]["subject"] == "normalization"
    for _ in range(limit):
        current = identity.request("GET", f"/interviews/{state['id']}").json()
        payload = {
            "question_id": current["current"]["id"],
            "text": "Normalization addresses functional dependencies.",
            "expected_revision": current["revision"],
            "idempotency_key": str(uuid4()),
        }
        assert (
            mutate(identity, "POST", f"/interviews/{state['id']}/answers", payload).status_code
            == 202
        )
        assert worker(identity, provider)
    return identity.request("GET", f"/learning/attempts/{attempt['id']}").json()


def test_complete_learning_retry_rag_improvement_resolution_reopen_loop(identity):
    _, gap = confirmed(identity)
    saved = plan(identity, gap["id"]).json()
    original = identity.sql(
        "select id, correctness, completeness from answer_evaluations order by id"
    )
    mutate(identity, "POST", f"/learning/plans/{saved['id']}/start", {"expected_revision": 0})
    payload = {
        "mode": "single",
        "gap_ids": [gap["id"]],
        "plan_id": saved["id"],
        "question_limit": 2,
        "idempotency_key": str(uuid4()),
    }
    retry = mutate(identity, "POST", "/learning/retries", payload)
    assert retry.status_code == 201, retry.text
    attempt = retry.json()
    assert attempt["parent_interview_id"]
    assert mutate(identity, "POST", "/learning/retries", payload).json()["id"] == attempt["id"]
    assert (
        mutate(
            identity, "POST", "/learning/retries", {**payload, "idempotency_key": str(uuid4())}
        ).json()["id"]
        == attempt["id"]
    )
    result = finish_retry(identity, attempt, 0.9, 2)
    first_comparison = result["comparison"]
    target = result["comparison"]["targets"][0]
    assert target["before"]["correctness"] == 0.25
    assert target["after"]["correctness"] == 0.9
    assert target["delta"]["correctness"] == 0.65
    assert target["gap_status"] == "improving" and len(target["retry_evidence_ids"]) == 2
    assert (
        identity.sql(
            "select id, correctness, completeness from answer_evaluations where id=ANY(%s) order by id",
            ([x["id"] for x in original],),
        )
        == original
    )
    second = mutate(
        identity,
        "POST",
        "/learning/retries",
        {**payload, "question_limit": 1, "idempotency_key": str(uuid4())},
    ).json()
    result = finish_retry(identity, second, 0.95, 1)
    assert result["comparison"]["targets"][0]["gap_status"] == "resolved"
    # New later independent weak checks use the same deterministic Phase 6 policy.
    owner = identity.sql("select candidate_id from learning_plans where id=%s", (saved["id"],))[0][
        "candidate_id"
    ]
    chunk = identity.sql("select id from knowledge_chunks limit 1")[0]["id"]
    engine, sessions = database(identity)

    async def decline():
        async with sessions() as db:
            for _ in range(3):
                _, _, evaluation = await make_evaluation(db, owner, chunk)
                await CandidateMemoryService.update(db, evaluation)
                await db.commit()
        await engine.dispose()

    run(decline())
    assert (
        identity.request("GET", f"/candidates/me/knowledge-gaps/{gap['id']}").json()["status"]
        == "confirmed"
    )
    assert (
        identity.request("GET", f"/learning/attempts/{attempt['id']}").json()["comparison"]
        == first_comparison
    )
    assert identity.request("GET", "/candidates/me/progress").json()["plans"][0]["stale"]


def test_retry_modes_invalid_selection_and_no_duplicate_scope(identity):
    _, gap = confirmed(identity)
    for mode, fields in [
        ("single", {"gap_ids": [gap["id"]]}),
        ("multiple", {"gap_ids": [gap["id"]]}),
        ("topic", {"subject": "DBMS"}),
        ("skill", {"subject": "SQL"}),
        ("recommended", {}),
    ]:
        response = mutate(
            identity,
            "POST",
            "/learning/retries",
            {"mode": mode, "idempotency_key": str(uuid4()), **fields},
        )
        assert response.status_code == 201, response.text
        state = identity.request("GET", f"/interviews/{response.json()['interview_id']}").json()
        assert state["configuration"]["selected_topics"] == ["DBMS"]
        assert not state["configuration"]["show_hints"]
    assert (
        mutate(
            identity,
            "POST",
            "/learning/retries",
            {"mode": "single", "idempotency_key": str(uuid4())},
        ).status_code
        == 422
    )
    assert (
        mutate(
            identity,
            "POST",
            "/learning/retries",
            {"mode": "topic", "subject": "Unknown", "idempotency_key": str(uuid4())},
        ).status_code
        == 409
    )


def test_learning_ownership_csrf_history_immutability_and_deletion(identity):
    _, gap = confirmed(identity)
    saved = plan(identity, gap["id"]).json()
    item = saved["items"][0]
    attempt = mutate(
        identity,
        "POST",
        f"/learning/items/{item['id']}/practice",
        {"idempotency_key": str(uuid4())},
    ).json()
    other = Harness(identity.url)
    assert other.register("other@example.com").status_code == 201
    assert other.login("other@example.com").status_code == 200
    for path in [
        f"/learning/plans/{saved['id']}",
        f"/learning/items/{item['id']}",
        f"/learning/attempts/{attempt['id']}",
    ]:
        assert other.request("GET", path).status_code == 404
    assert plan(other, gap["id"]).status_code == 404
    assert (
        mutate(
            other, "POST", f"/learning/items/{item['id']}/complete", {"expected_revision": 0}
        ).status_code
        == 404
    )
    assert (
        mutate(
            other, "POST", f"/knowledge-gaps/{gap['id']}/retry", {"idempotency_key": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        identity.request(
            "POST",
            "/learning/plans",
            json={"gap_ids": [gap["id"]], "idempotency_key": str(uuid4())},
        ).status_code
        == 403
    )
    assert Harness(identity.url).request("GET", "/learning/plans").status_code == 401
    import psycopg

    with pytest.raises(psycopg.errors.RaiseException):
        identity.sql("update learning_targets set priority=0 where plan_id=%s", (saved["id"],))
    identity.sql("delete from users where email=%s", ("candidate@example.com",))
    for table in [
        "learning_plans",
        "learning_items",
        "learning_targets",
        "learning_attempts",
        "learning_actions",
    ]:
        assert identity.sql(f"select count(*) as n from {table}")[0]["n"] == 0


def test_concurrent_learning_plan_creation_serializes_and_reuses(identity):
    owner, gap = confirmed(identity)
    engine, sessions = database(identity)

    async def create_one():
        async with sessions() as db:
            row = await learning.create_plan(
                db, owner, PlanInput(gap_ids=[UUID(gap["id"])], idempotency_key=uuid4())
            )
            await db.commit()
            return row.id

    async def concurrent():
        results = await asyncio.gather(create_one(), create_one())
        assert results[0] == results[1]
        await engine.dispose()

    run(concurrent())


def test_grounded_learning_generation_validated_sources_and_stale_revision(identity):
    owner, gap = confirmed(identity)
    saved = plan(identity, gap["id"]).json()
    engine, sessions = database(identity)

    class ContentProvider:
        name, model = "test", "learning-content"
        invalid = False

        async def structured(self, *, system, user, schema, name):
            assert "untrusted" in system and schema == LearningContent
            context = json.loads(user.removeprefix("<DATA>\n").removesuffix("\n</DATA>"))
            chunk = context["retrieved_sources"][0]["chunk_id"]
            return LearningContent(
                explanation="Transactions preserve related writes.",
                examples=["Save related records atomically."],
                practice_question="Explain how related database writes stay consistent.",
                hints=[],
                source_chunk_ids=[uuid4() if self.invalid else UUID(chunk)],
            )

    provider = ContentProvider()
    item_id = UUID(saved["items"][0]["id"])

    async def generate():
        result = await learning.generate_content(
            sessions, owner, item_id, 0, provider, FakeEmbeddingProvider()
        )
        assert result["content"]["grounding_status"] == "source_cited_generated"
        assert result["content"]["sources"]
        provider.invalid = True
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await learning.generate_content(
                sessions, owner, item_id, 1, provider, FakeEmbeddingProvider()
            )
        with pytest.raises(HTTPException):
            await learning.generate_content(
                sessions, owner, item_id, 0, provider, FakeEmbeddingProvider()
            )
        async with sessions() as db:
            assert (await db.get(LearningItem, item_id)).content_revision == 1
            assert len((await db.scalars(select(LearningPlan))).all()) == 1
        await engine.dispose()

    run(generate())


def test_learning_policy_requires_repeated_independent_recovery():
    from app.services.memory_policy import gap_decision

    weak = [observation(0.25, when=i) for i in range(3)]
    assert gap_decision(weak, "learning", 0.25).status == "learning"
    strong = [observation(0.9, when=i + 3) for i in range(3)]
    assert gap_decision(weak + strong[:1], "learning", 0.25).status == "learning"
    assert gap_decision(weak + strong[:2], "learning", 0.25).status == "improving"
    assert gap_decision(weak + strong, "learning", 0.25).status == "resolved"


def test_concurrent_retry_and_lexical_learning_retrieval(identity):
    owner, gap = confirmed(identity)
    engine, sessions = database(identity)

    async def create_one():
        async with sessions() as db:
            attempt = await learning.retry(
                db,
                owner,
                RetryInput(mode="single", gap_ids=[UUID(gap["id"])], idempotency_key=uuid4()),
            )
            await db.commit()
            return attempt.id

    async def check():
        ids = await asyncio.gather(create_one(), create_one())
        assert ids[0] == ids[1]
        async with sessions() as db:
            content = await learning.source_content(db, "API reliability", "transactions")
            assert content["retrieval_method"] == "lexical"
            assert content["grounding_status"] == "source_extract"
            assert content["sources"][0]["content"] in content["explanation"]
            missing = await learning.source_content(db, "Absent topic", "Unknown concept")
            assert not missing["sources"] and missing["grounding_status"] == "insufficient"
        await engine.dispose()

    run(check())


def test_retry_question_cannot_repeat_the_baseline():
    from app.providers.llm import LLMOutputError
    from app.services.interviews import check_retry_question

    context = {
        "retry_targets": [{"baseline": {"questions": ["Explain normalization using this table."]}}]
    }
    with pytest.raises(LLMOutputError):
        check_retry_question(
            SimpleNamespace(question="Explain normalization using this table."), context
        )
    check_retry_question(
        SimpleNamespace(question="Compare BCNF trade-offs using a new schema."), context
    )
