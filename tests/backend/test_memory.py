import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.models import Base
from app.models.interviews import (
    AnswerEvaluation,
    Interview,
    InterviewAnswer,
    InterviewQuestion,
    InterviewRound,
)
from app.models.knowledge import EvaluationSource
from app.models.memory import CandidateMemory, KnowledgeGap, MemoryEvidence
from app.providers.llm import LLMProvider
from app.schemas.interviews import GroundedEvaluationResult, PlanResult, QuestionResult
from app.services.interviews import context_snapshot
from app.services.memory import CandidateMemoryService
from app.services.memory_policy import gap_decision, independent
from conftest import Harness, run
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_interviews import (
    create_interview,
    mutate,
    seed_knowledge,
    signed_in,
    worker,
)


def observation(score, interview=None, root=None, when=0, grounded=True, confidence=0.9):
    return SimpleNamespace(
        id=uuid4(),
        evaluation_id=uuid4(),
        root_question_id=root or uuid4(),
        interview_id=interview or uuid4(),
        correctness=score,
        confidence=confidence,
        grounded=grounded,
        assisted=False,
        question_hash=uuid4().hex,
        weak=score < 0.6,
        strong=score >= 0.8,
        observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=when),
    )


def test_policy_single_weak_is_only_observed_and_followup_correction_is_correlated():
    root = uuid4()
    first = observation(0.2, root=root)
    assert gap_decision([first]).status == "observed"
    second = observation(0.9, root=root, interview=first.interview_id, when=1)
    assert len(independent([first, second])) == 1
    assert not independent([first, second])[0].weak


def test_migration_matches_model_metadata(test_database):
    engine = create_engine(test_database)
    try:
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()


def test_policy_repeats_improvement_resolution_and_reopening():
    a, b = uuid4(), uuid4()
    weak = [observation(0.2, a), observation(0.3, a, when=1), observation(0.25, b, when=2)]
    assert gap_decision(weak).status == "confirmed"
    assert gap_decision([observation(0.1, a, when=i) for i in range(5)]).status == "observed"
    good = [observation(0.85, when=3), observation(0.9, when=4), observation(0.95, when=5)]
    assert gap_decision(weak + good[:1], "confirmed", 0.25).status == "confirmed"
    assert gap_decision(weak + good[:2], "confirmed", 0.25).status == "improving"
    assert gap_decision(weak + good, "improving", 0.25).status == "resolved"
    resolved_at = good[-1].observed_at
    new_weak = [observation(0.2, when=6), observation(0.25, when=7), observation(0.1, when=8)]
    assert (
        gap_decision(weak + good + new_weak[:1], "resolved", 0.25, resolved_at).status == "resolved"
    )
    assert gap_decision(weak + good + new_weak, "resolved", 0.25, resolved_at).status == "confirmed"


def test_policy_insufficient_and_low_confidence_never_confirm():
    assert (
        gap_decision([observation(0.1, grounded=False, when=i) for i in range(6)]).status
        == "observed"
    )


def test_policy_hints_and_repeated_questions_cannot_prove_recovery():
    values = [observation(0.2, when=i) for i in range(3)]
    for value in values:
        value.assisted = True
    assert gap_decision(values).status == "observed"
    good = [observation(0.9, when=i + 3) for i in range(3)]
    for value in good:
        value.question_hash = "same-question"
    assert gap_decision(good, "confirmed", 0.25).status == "improving"
    assert (
        gap_decision([observation(0.1, confidence=0.5, when=i) for i in range(6)]).status
        == "observed"
    )


async def make_evaluation(
    db,
    owner,
    chunk,
    *,
    score=0.25,
    interview=None,
    sequence=1,
    parent=None,
    misconception=True,
    mode="practice",
    completed=True,
):
    if interview is None:
        interview = Interview(
            candidate_id=owner,
            interview_type="technical",
            mode=mode,
            status="completed" if completed else "evaluating",
            revision=1,
            question_limit=6,
            configuration={"selected_topics": ["DBMS"], "difficulty": 2, "use_memory": True},
        )
        db.add(interview)
        await db.flush()
        round_row = InterviewRound(
            interview_id=interview.id,
            ordinal=1,
            title="DBMS",
            topic="DBMS",
            objective="Check normalization",
            question_budget=6,
            initial_difficulty=2,
            status="active",
        )
        db.add(round_row)
        await db.flush()
    else:
        round_row = await db.scalar(
            select(InterviewRound).where(InterviewRound.interview_id == interview.id)
        )
    question = InterviewQuestion(
        interview_id=interview.id,
        round_id=round_row.id,
        sequence=sequence,
        text=f"Explain normalization and 3NF in example {sequence}.",
        topic="DBMS",
        skill="SQL",
        difficulty=2,
        question_type="technical",
        reason="Assess schema reasoning",
        state="answered",
        operation_id=uuid4(),
        parent_question_id=parent,
    )
    db.add(question)
    await db.flush()
    answer = InterviewAnswer(
        interview_id=interview.id,
        question_id=question.id,
        candidate_id=owner,
        sequence=sequence,
        text="Third normal form relates to functional dependencies.",
        status="evaluated",
        idempotency_key=uuid4(),
        payload_hash="a" * 64,
    )
    db.add(answer)
    await db.flush()
    evaluation = AnswerEvaluation(
        interview_id=interview.id,
        answer_id=answer.id,
        correctness=score,
        relevance=score,
        completeness=score,
        technical_depth=score,
        reasoning=score,
        clarity=0.8,
        confidence=0.9,
        strengths=[] if score < 0.8 else ["Explained dependencies"],
        weaknesses=["Incomplete normalization explanation"] if score < 0.6 else [],
        missing_concepts=["normalization"] if score < 0.6 else [],
        misconceptions=["3NF removes every dependency"] if misconception else [],
        evidence=["Third normal form"],
        feedback="Review the stated dependency rules.",
        prompt_version="fixture",
        provider="test",
        model="test",
        grounding_status="grounded" if chunk else "insufficient",
        evaluation_notes="Reference-backed fixture",
    )
    db.add(evaluation)
    await db.flush()
    if chunk:
        db.add(
            EvaluationSource(
                evaluation_id=evaluation.id,
                chunk_id=chunk,
                retrieval_rank=1,
                similarity=0.9,
                relationship="contradicts" if score < 0.6 else "supports",
                supported_claim="Normalization controls dependency anomalies.",
            )
        )
    await db.flush()
    return interview, question, evaluation


def database(identity):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def setup(identity):
    signed_in(identity)
    seed_knowledge(identity)
    owner = identity.sql(
        "SELECT id FROM candidates WHERE user_id=(SELECT id FROM users WHERE email=%s)",
        ("candidate@example.com",),
    )[0]["id"]
    chunk = identity.sql("SELECT id FROM knowledge_chunks LIMIT 1")[0]["id"]
    return owner, chunk


def test_persistent_gap_journey_history_context_privacy_and_immutability(identity):
    owner, chunk = setup(identity)
    engine, sessions = database(identity)

    async def scenario():
        async with sessions() as db:
            first, q, e = await make_evaluation(db, owner, chunk)
            await CandidateMemoryService.update(db, e)
            await db.commit()
            evidence_id = await db.scalar(select(MemoryEvidence.id).limit(1))
            first_id = first.id
        async with sessions() as db:
            gaps = await CandidateMemoryService.gaps(db, owner)
            assert gaps and all(x["status"] == "observed" for x in gaps)
            first = await db.get(Interview, first_id)
            _, _, e = await make_evaluation(db, owner, chunk, interview=first, sequence=2)
            await CandidateMemoryService.update(db, e)
            second, _, e2 = await make_evaluation(db, owner, chunk)
            await CandidateMemoryService.update(db, e2)
            await CandidateMemoryService.update(db, e2)  # Replay is a no-op.
            await db.commit()
            draft = Interview(
                candidate_id=owner,
                interview_type="technical",
                mode="practice",
                status="created",
                question_limit=3,
                configuration={"selected_topics": ["DBMS"], "use_memory": True},
            )
            db.add(draft)
            await db.flush()
            context = await context_snapshot(db, draft)
            assert any(
                x["subject"] == "normalization" for x in context["candidate_memory"]["items"]
            )
            draft.configuration = {"selected_topics": ["Python"], "use_memory": True}
            assert not (await context_snapshot(db, draft))["candidate_memory"]["items"]
            draft.configuration = {"selected_topics": ["DBMS"], "use_memory": False}
            assert not (await context_snapshot(db, draft))["candidate_memory"]["enabled"]
        async with sessions() as db:
            third, _, e = await make_evaluation(db, owner, chunk, score=0.9, misconception=False)
            await CandidateMemoryService.update(db, e)
            _, _, e = await make_evaluation(
                db, owner, chunk, interview=third, sequence=2, score=0.95, misconception=False
            )
            await CandidateMemoryService.update(db, e)
            await db.commit()
        async with sessions() as db:
            concept = await db.scalar(
                select(CandidateMemory).where(
                    CandidateMemory.candidate_id == owner, CandidateMemory.kind == "concept"
                )
            )
            gap = await db.scalar(select(KnowledgeGap).where(KnowledgeGap.memory_id == concept.id))
            assert gap.status == "improving"
            _, _, e = await make_evaluation(db, owner, chunk, score=0.9, misconception=False)
            await CandidateMemoryService.update(db, e)
            await db.commit()
            await db.refresh(gap)
            assert gap.status == "resolved"
            history = await CandidateMemoryService.history(db, owner, "skill")
            assert len(history[0]["history"]) == 6
            detail = await CandidateMemoryService.gap_detail(db, owner, gap.id)
            assert len(detail["evidence"]) == 6
            assert [x["to_status"] for x in detail["transitions"]] == [
                "observed",
                "confirmed",
                "improving",
                "resolved",
            ]
            assert detail["evidence"][0]["sources"]
            result = (gap.id, concept.id, evidence_id)
        await engine.dispose()
        return result

    gap_id, memory_id, evidence_id = run(scenario())
    skills = identity.request("GET", "/candidates/me/skills/history")
    assert skills.status_code == 200 and len(skills.json()[0]["history"]) == 6
    misconceptions = identity.request("GET", "/candidates/me/misconceptions").json()
    assert misconceptions[0]["status"] == "resolved" and misconceptions[0]["evidence_count"] == 6
    original = identity.sql("SELECT correctness FROM memory_evidence WHERE id=%s", (evidence_id,))[
        0
    ]
    with pytest.raises(psycopg.Error, match="immutable"):
        identity.sql("UPDATE memory_evidence SET correctness=1 WHERE id=%s", (evidence_id,))
    assert (
        identity.sql("SELECT correctness FROM memory_evidence WHERE id=%s", (evidence_id,))[0]
        == original
    )
    other = Harness(identity.url)
    assert other.register("other-memory@example.com").status_code == 201
    assert other.login("other-memory@example.com").status_code == 200
    assert other.request("GET", "/candidates/me/knowledge-gaps").json() == []
    assert other.request("GET", f"/candidates/me/knowledge-gaps/{gap_id}").status_code == 404
    assert other.request("GET", f"/candidates/me/memory/{memory_id}/evidence").status_code == 404
    assert Harness(identity.url).request("GET", "/candidates/me/memory").status_code == 401


def test_concurrent_updates_are_idempotent_and_simulation_is_hidden(identity):
    owner, chunk = setup(identity)
    engine, sessions = database(identity)

    async def scenario():
        async with sessions() as db:
            interview, _, evaluation = await make_evaluation(
                db, owner, chunk, mode="simulation", completed=False
            )
            await CandidateMemoryService.update(db, evaluation)
            assert (await CandidateMemoryService.memories(db, owner)) == []
            interview.status = "completed"
            await db.commit()
            evaluation_id = evaluation.id

        async def replay():
            async with sessions() as db:
                evaluation = await db.get(AnswerEvaluation, evaluation_id)
                await CandidateMemoryService.update(db, evaluation)
                await db.commit()

        await asyncio.gather(replay(), replay())
        async with sessions() as db:
            rows = (
                await db.scalars(select(MemoryEvidence).where(MemoryEvidence.candidate_id == owner))
            ).all()
            assert rows and len(rows) == len({x.memory_id for x in rows})
        await engine.dispose()

    run(scenario())
    identity.sql("DELETE FROM users WHERE email=%s", ("candidate@example.com",))
    assert (
        identity.sql(
            "SELECT count(*) AS count FROM memory_evidence WHERE candidate_id=%s", (owner,)
        )[0]["count"]
        == 0
    )


def test_insufficient_rag_creates_only_provisional_evidence(identity):
    owner, _ = setup(identity)
    engine, sessions = database(identity)

    async def scenario():
        async with sessions() as db:
            for _ in range(4):
                _, _, evaluation = await make_evaluation(db, owner, None)
                await CandidateMemoryService.update(db, evaluation)
            await db.commit()
            gaps = await CandidateMemoryService.gaps(db, owner)
            assert gaps and all(x["provisional"] and x["independent_count"] == 0 for x in gaps)
        await engine.dispose()

    run(scenario())


class MemoryJourneyProvider(LLMProvider):
    name = "test"
    model = "memory-journey"

    def __init__(self, score):
        self.score = score
        self.questions = 0
        self.planning_context = None

    async def structured(self, *, system, user, schema, name):
        data = json.loads(user.removeprefix("<DATA>\n").removesuffix("\n</DATA>"))
        if schema is PlanResult:
            self.planning_context = data
            return PlanResult(
                objectives=["Assess normalization"],
                topics=[
                    {
                        "title": "DBMS",
                        "objective": "Evaluate normalization",
                        "question_budget": 2,
                        "initial_difficulty": 2,
                        "skill": "SQL",
                    }
                ],
            )
        if schema is QuestionResult:
            self.questions += 1
            return QuestionResult(
                question=f"Explain normalization and 3NF using design example {self.questions}.",
                topic="DBMS",
                skill="SQL",
                difficulty=2,
                question_type="technical",
                reason="Check dependency reasoning",
            )
        assert schema is GroundedEvaluationResult
        chunks = data["retrieved_knowledge"]
        assert chunks
        return GroundedEvaluationResult(
            correctness=self.score,
            relevance=self.score,
            completeness=self.score,
            technical_depth=self.score,
            reasoning=self.score,
            clarity=0.8,
            strengths=["Explained functional dependencies"] if self.score >= 0.8 else [],
            weaknesses=["Incomplete normalization explanation"] if self.score < 0.6 else [],
            missing_concepts=["normalization"] if self.score < 0.6 else [],
            misconceptions=["3NF removes every dependency"] if self.score < 0.6 else [],
            evidence=["functional dependencies"],
            feedback="Evidence-backed fixture feedback",
            hint=None,
            confidence=0.9,
            grounding_status="grounded",
            evaluation_notes="Compared with retrieved sources",
            knowledge_evidence=[
                {
                    "knowledge_chunk_id": chunks[0]["knowledge_chunk_id"],
                    "claim": "Normalization controls dependency anomalies",
                    "relationship": "supports",
                }
            ],
        )


def test_multi_interview_rag_memory_worker_journey(identity):
    setup(identity)
    contexts = []
    for index, score in enumerate([0.25, 0.3, 0.2, 0.9, 0.95]):
        created = create_interview(identity, selected_topics=["DBMS"], show_hints=False).json()
        assert (
            mutate(
                identity,
                "POST",
                f"/interviews/{created['id']}/start",
                {"expected_revision": created["revision"]},
            ).status_code
            == 202
        )
        provider = MemoryJourneyProvider(score)
        assert worker(identity, provider)
        contexts.append(provider.planning_context)
        for _ in range(2):
            state = identity.request("GET", f"/interviews/{created['id']}").json()
            assert state["status"] == "waiting_for_answer"
            submitted = mutate(
                identity,
                "POST",
                f"/interviews/{created['id']}/answers",
                {
                    "question_id": state["current"]["id"],
                    "text": "Normalization addresses functional dependencies.",
                    "expected_revision": state["revision"],
                    "idempotency_key": str(uuid4()),
                },
            )
            assert submitted.status_code == 202
            assert worker(identity, provider)
        state = identity.request("GET", f"/interviews/{created['id']}").json()
        assert state["status"] == "completed"
        gaps = identity.request("GET", "/candidates/me/knowledge-gaps").json()
        concept = next(
            x for x in gaps if x["kind"] == "concept" and x["subject"] == "normalization"
        )
        assert (
            concept["status"]
            == ["observed", "observed", "confirmed", "improving", "resolved"][index]
        )
    # Weak follow-ups are correlated, so each of the first two interviews supplies
    # one weak root only. Another weak interview is required before confirmation.
    assert contexts[1]["candidate_memory"]["items"] == []
    assert any(x["subject"] == "normalization" for x in contexts[3]["candidate_memory"]["items"])
    assert (
        identity.request("GET", "/candidates/me/concepts/history").json()[0]["evidence_count"] == 10
    )
