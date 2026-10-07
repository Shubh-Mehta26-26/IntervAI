import json
from uuid import uuid4

from app.api.interviews import require_llm_ready
from app.main import app
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LLMProvider, strict_json_schema
from app.schemas.interviews import (
    EvaluationResult,
    GroundedEvaluationResult,
    PlanResult,
    QuestionResult,
)
from app.services.adaptive import decide
from app.services.knowledge import ingest_document
from app.worker import process_interview_one
from conftest import PASSWORD, Harness, run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class FakeProvider(LLMProvider):
    name = "test"
    model = "deterministic-v1"

    def __init__(self):
        self.calls = []

    async def structured(self, *, system, user, schema, name):
        self.calls.append((name, user))
        if schema is PlanResult:
            return PlanResult.model_validate(
                {
                    "objectives": ["Assess grounded backend engineering decisions"],
                    "topics": [
                        {
                            "title": "Python APIs",
                            "objective": "Explore API design using the candidate evidence",
                            "question_budget": 2,
                            "initial_difficulty": 2,
                            "skill": "Python",
                        }
                    ],
                }
            )
        if schema is QuestionResult:
            follow_up = '"adaptive_action":"increase_difficulty"' in user
            return QuestionResult.model_validate(
                {
                    "question": (
                        "How would you make that FastAPI design reliable under concurrent load?"
                        if follow_up
                        else "Why did you choose FastAPI for the API project described in your evidence?"
                    ),
                    "topic": "Python APIs",
                    "skill": "FastAPI",
                    "difficulty": 3 if follow_up else 2,
                    "question_type": "follow_up" if follow_up else "project",
                    "reason": "Grounded in the supplied project and role evidence.",
                }
            )
        assert schema is GroundedEvaluationResult
        context = json.loads(user.removeprefix("<DATA>\n").removesuffix("\n</DATA>"))
        retrieved = context.get("retrieved_knowledge", [])
        return GroundedEvaluationResult.model_validate(
            {
                "correctness": 0.9,
                "relevance": 0.9,
                "completeness": 0.85,
                "technical_depth": 0.8,
                "reasoning": 0.85,
                "clarity": 0.9,
                "strengths": ["Explained validation and async trade-offs"],
                "weaknesses": ["Could quantify capacity assumptions"],
                "missing_concepts": [],
                "misconceptions": [],
                "evidence": ["I used typed validation and async handlers"],
                "feedback": "Good evidence-backed explanation with a clear design rationale.",
                "hint": "Consider connection pools and backpressure.",
                "confidence": 0.88,
                "knowledge_evidence": (
                    [
                        {
                            "knowledge_chunk_id": retrieved[0]["knowledge_chunk_id"],
                            "claim": "Transactions keep related writes consistent.",
                            "relationship": "supports",
                        }
                    ]
                    if retrieved
                    else []
                ),
                "evaluation_notes": (
                    "The cited source supports the transaction claim."
                    if retrieved
                    else "No matching curated chunks were available in this fixture."
                ),
                "grounding_status": "grounded" if retrieved else "insufficient",
            }
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "test"
    model = "test-embedding-v1"
    dimensions = 1536

    async def embed(self, texts):
        return [[1.0] + [0.0] * 1535 for _ in texts]


def signed_in(identity):
    assert identity.register().status_code == 201
    assert identity.login().status_code == 200
    app.dependency_overrides[require_llm_ready] = lambda: None
    return identity


def mutate(identity, method, path, payload):
    return identity.request(method, path, headers={"X-CSRF-Token": identity.csrf}, json=payload)


def worker(identity, provider):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def work():
        try:
            return await process_interview_one(factory, provider, FakeEmbeddingProvider())
        finally:
            await engine.dispose()

    return run(work())


def create_interview(identity, **values):
    payload = {
        "interview_type": "technical",
        "mode": "practice",
        "question_limit": 2,
        "duration_minutes": 20,
        "selected_topics": ["Python", "FastAPI"],
        "difficulty": 2,
        "candidate_focus": "API architecture",
        "instructions": "Ask for trade-offs",
        "show_hints": True,
        **values,
    }
    return mutate(identity, "POST", "/interviews", payload)


def seed_knowledge(identity):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed():
        try:
            async with factory() as db:
                await ingest_document(
                    db,
                    FakeEmbeddingProvider(),
                    title="API Transactions",
                    source="intervai://test/api-transactions",
                    source_type="test",
                    domain="Python",
                    topic="API reliability",
                    text="# API Transactions\n\n" + (
                        "Database transactions keep related writes consistent and should be short. "
                        * 20
                    ),
                )
        finally:
            await engine.dispose()

    run(seed())


def test_adaptive_policy_deterministic_actions():
    base = {
        "relevance": 0.8,
        "technical_depth": 0.7,
        "clarity": 0.8,
        "strengths": [],
        "weaknesses": [],
        "evidence": [],
        "feedback": "Evidence-based feedback",
        "hint": None,
        "confidence": 0.8,
    }
    strong = EvaluationResult(
        correctness=0.9,
        completeness=0.85,
        reasoning=0.8,
        missing_concepts=[],
        misconceptions=[],
        **base,
    )
    assert (
        decide(
            strong, current_difficulty=2, topic="Python", answered_count=1, question_limit=4
        ).action
        == "increase_difficulty"
    )
    partial = strong.model_copy(update={"correctness": 0.65, "completeness": 0.55})
    assert (
        decide(
            partial, current_difficulty=2, topic="Python", answered_count=1, question_limit=4
        ).action
        == "ask_follow_up"
    )
    missing = partial.model_copy(update={"missing_concepts": ["transactions"]})
    assert (
        decide(
            missing, current_difficulty=2, topic="SQL", answered_count=1, question_limit=4
        ).action
        == "test_missing_concept"
    )
    assert (
        decide(
            partial,
            current_difficulty=3,
            topic="SQL",
            answered_count=2,
            question_limit=5,
            topic_weak_count=2,
        ).action
        == "revisit_topic"
    )
    assert (
        decide(
            strong, current_difficulty=5, topic="Python", answered_count=4, question_limit=4
        ).action
        == "end_interview"
    )


def test_provider_schema_is_strict_at_every_object_boundary():
    schema = strict_json_schema(EvaluationResult.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_full_practice_interview_persists_plan_evaluation_decision_and_completion(identity):
    signed_in(identity)
    profile = identity.request("GET", "/candidates/me").json()
    identity.patch(
        {
            "expected_revision": profile["revision"],
            "display_name": profile["display_name"],
            "phone": None,
            "location": "Pune",
            "headline": "Backend engineer",
            "biography": "Built a FastAPI interview application with PostgreSQL.",
            "timezone": "Asia/Calcutta",
            "experience_months": 36,
            "career_interests": ["Backend engineering"],
            "goals": [],
            "education": [],
            "experience": [],
            "preferences": profile["preferences"],
        }
    )
    job = mutate(
        identity,
        "POST",
        "/jobs",
        {
            "title": "Backend Engineer",
            "description": "Required Skills:\nPython\nFastAPI\nPostgreSQL\nResponsibilities:\nBuild reliable APIs.",
        },
    ).json()
    created = create_interview(identity, job_id=job["id"])
    assert created.status_code == 201
    interview = created.json()
    assert interview["status"] == "created"
    started = mutate(
        identity, "POST", f"/interviews/{interview['id']}/start", {"expected_revision": 0}
    )
    assert started.status_code == 202
    provider = FakeProvider()
    assert worker(identity, provider)
    ready = identity.request("GET", f"/interviews/{interview['id']}").json()
    assert ready["status"] == "waiting_for_answer"
    assert ready["plan"]["topics"][0]["title"] == "Python APIs"
    assert "Backend Engineer" in provider.calls[0][1]
    assert "FastAPI interview application" in provider.calls[0][1]
    seed_knowledge(identity)

    key = str(uuid4())
    payload = {
        "question_id": ready["current"]["id"],
        "text": "I used typed validation and async handlers, with transactions for consistent writes.",
        "duration_seconds": 45,
        "expected_revision": ready["revision"],
        "idempotency_key": key,
    }
    submitted = mutate(identity, "POST", f"/interviews/{interview['id']}/answers", payload)
    assert submitted.status_code == 202
    duplicate = mutate(identity, "POST", f"/interviews/{interview['id']}/answers", payload)
    assert (
        duplicate.status_code == 202
        and duplicate.json()["operation_id"] == submitted.json()["operation_id"]
    )
    conflict = mutate(
        identity, "POST", f"/interviews/{interview['id']}/answers", {**payload, "text": "different"}
    )
    assert conflict.status_code == 409
    stale = mutate(
        identity,
        "POST",
        f"/interviews/{interview['id']}/pause",
        {"expected_revision": ready["revision"]},
    )
    assert stale.status_code == 409
    assert worker(identity, provider)
    next_state = identity.request("GET", f"/interviews/{interview['id']}").json()
    assert next_state["current"]["difficulty"] == 3
    assert next_state["practice_feedback"]["correctness"] == 0.9
    assert next_state["practice_feedback"]["grounding_status"] == "grounded"
    assert next_state["practice_feedback"]["knowledge_evidence"][0]["title"] == "API Transactions"
    logs = identity.sql(
        "SELECT results, retrieval_version FROM retrieval_logs WHERE interview_id = %s",
        (interview["id"],),
    )
    assert logs and logs[0]["retrieval_version"] == "rag-v1" and logs[0]["results"]
    assert next_state["practice_decision"]["action"] == "increase_difficulty"
    memory = identity.request("GET", "/candidates/me/memory")
    assert memory.status_code == 200 and memory.json()["items"]
    assert identity.request("GET", "/candidates/me/skills/history").json()

    second = {
        "question_id": next_state["current"]["id"],
        "text": "I would use pool limits, timeouts, and backpressure, then measure p95 latency.",
        "duration_seconds": 35,
        "expected_revision": next_state["revision"],
        "idempotency_key": str(uuid4()),
    }
    assert (
        mutate(identity, "POST", f"/interviews/{interview['id']}/answers", second).status_code
        == 202
    )
    assert worker(identity, provider)
    complete = identity.request("GET", f"/interviews/{interview['id']}").json()
    assert complete["status"] == "completed"
    assert complete["summary"]["evaluated_answers"] == 2
    assert len(identity.sql("SELECT * FROM answer_evaluations")) == 2
    assert len(identity.sql("SELECT * FROM adaptive_decisions")) == 2
    assert identity.request("GET", f"/interviews/{interview['id']}/summary").status_code == 200


def test_simulation_hides_feedback_and_enforces_ownership_and_states(identity):
    signed_in(identity)
    created = create_interview(
        identity, mode="simulation", question_limit=2, show_hints=True
    ).json()
    assert created["configuration"]["show_hints"] is False
    assert (
        mutate(
            identity, "POST", f"/interviews/{created['id']}/start", {"expected_revision": 0}
        ).status_code
        == 202
    )
    provider = FakeProvider()
    assert worker(identity, provider)
    ready = identity.request("GET", f"/interviews/{created['id']}").json()
    assert (
        mutate(
            identity,
            "POST",
            f"/interviews/{created['id']}/start",
            {"expected_revision": ready["revision"]},
        ).status_code
        == 409
    )
    payload = {
        "question_id": ready["current"]["id"],
        "text": "A clear answer with technical trade-offs.",
        "duration_seconds": 20,
        "expected_revision": ready["revision"],
        "idempotency_key": str(uuid4()),
    }
    assert (
        mutate(identity, "POST", f"/interviews/{created['id']}/answers", payload).status_code == 202
    )
    assert worker(identity, provider)
    hidden = identity.request("GET", f"/interviews/{created['id']}/answers").json()
    assert hidden[0]["evaluation"] is None and hidden[0]["decision"] is None
    assert identity.request("GET", "/candidates/me/memory").json()["items"] == []

    other = Harness(identity.url)
    assert other.register("interview-other@example.com").status_code == 201
    assert other.login("interview-other@example.com", PASSWORD).status_code == 200
    assert other.request("GET", f"/interviews/{created['id']}").status_code == 404
    assert (
        mutate(
            other, "POST", f"/interviews/{created['id']}/cancel", {"expected_revision": 0}
        ).status_code
        == 404
    )


def test_validation_auth_and_missing_provider(identity):
    signed_in(identity)
    invalid = create_interview(identity, question_limit=31)
    assert invalid.status_code == 422
    created = create_interview(identity).json()
    app.dependency_overrides.pop(require_llm_ready)
    missing = mutate(
        identity, "POST", f"/interviews/{created['id']}/start", {"expected_revision": 0}
    )
    assert missing.status_code == 503 and missing.json()["error"]["code"] == "llm_not_configured"
    anonymous = Harness(identity.url)
    assert anonymous.request("GET", "/interviews").status_code == 401
