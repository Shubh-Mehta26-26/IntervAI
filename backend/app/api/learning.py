from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.api.interviews import require_llm_ready
from app.db.session import SessionFactory
from app.models.learning import LearningAttempt, LearningItem, LearningPlan
from app.providers.embeddings import get_embedding_provider
from app.providers.llm import get_provider
from app.schemas.interviews import AnswerInput
from app.schemas.learning import PlanInput, PracticeInput, RetryInput, RevisionInput
from app.services import learning as service
from app.services.interviews import candidate

router = APIRouter(tags=["learning"])
mutation = [Depends(csrf_actor)]


@router.get("/learning/plans")
async def plans(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    rows = (
        await db.scalars(
            select(LearningPlan)
            .where(LearningPlan.candidate_id == owner.id)
            .order_by(LearningPlan.created_at.desc())
            .limit(50)
        )
    ).all()
    return [await service.plan_value(db, x) for x in rows]


@router.post("/learning/plans", dependencies=mutation, status_code=201)
async def create(payload: PlanInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    plan = await service.create_plan(db, owner.id, payload)
    await db.commit()
    return await service.plan_value(db, plan)


@router.post("/knowledge-gaps/{identifier}/learning-plan", dependencies=mutation, status_code=201)
async def gap_plan(identifier: UUID, payload: PracticeInput, actor: CandidateActor, db: DB):
    return await create(
        PlanInput(gap_ids=[identifier], idempotency_key=payload.idempotency_key), actor, db
    )


@router.get("/learning/plans/{identifier}")
async def detail(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.plan_value(db, await service.owned(db, LearningPlan, identifier, owner.id))


@router.post("/learning/plans/{identifier}/start", dependencies=mutation)
async def start(identifier: UUID, payload: RevisionInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    plan = await service.start_learning(db, owner.id, identifier, payload.expected_revision)
    await db.commit()
    await db.refresh(plan)
    return await service.plan_value(db, plan)


@router.get("/learning/items/{identifier}")
async def item(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return service.item_value(await service.owned(db, LearningItem, identifier, owner.id))


@router.post("/learning/items/{identifier}/complete", dependencies=mutation)
async def complete(identifier: UUID, payload: RevisionInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    plan = await service.complete_item(db, owner.id, identifier, payload.expected_revision)
    await db.commit()
    await db.refresh(plan)
    return await service.plan_value(db, plan)


@router.post(
    "/learning/items/{identifier}/generate",
    dependencies=[Depends(csrf_actor), Depends(require_llm_ready)],
)
async def generate(identifier: UUID, payload: RevisionInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    owner_id = owner.id
    # Release request session before provider work.
    await service.owned(db, LearningItem, identifier, owner.id)
    await db.rollback()
    from pydantic import ValidationError

    from app.core.errors import fail
    from app.providers.embeddings import EmbeddingError
    from app.providers.llm import LLMError

    try:
        return await service.generate_content(
            SessionFactory,
            owner_id,
            identifier,
            payload.expected_revision,
            get_provider(),
            get_embedding_provider(),
        )
    except (LLMError, EmbeddingError, ValidationError):
        fail(
            503,
            "learning_generation_failed",
            "Learning content could not be validated or generated. Your saved content is unchanged; try again.",
        )


@router.post("/learning/items/{identifier}/practice", dependencies=mutation, status_code=201)
async def practice(identifier: UUID, payload: PracticeInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    attempt = await service.practice(db, owner.id, identifier, payload.idempotency_key)
    await db.commit()
    return await service.attempt_value(db, attempt)


@router.get("/learning/attempts/{identifier}")
async def attempt(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    return await service.attempt_value(
        db, await service.owned(db, LearningAttempt, identifier, owner.id)
    )


@router.post(
    "/learning/items/{identifier}/practice/{attempt_id}/submit",
    dependencies=[Depends(csrf_actor), Depends(require_llm_ready)],
    status_code=202,
)
async def submit(
    identifier: UUID, attempt_id: UUID, payload: AnswerInput, actor: CandidateActor, db: DB
):
    from app.api.interviews import submit_answer
    from app.core.errors import fail

    owner = await candidate(db, actor.user.id)
    await service.owned(db, LearningItem, identifier, owner.id)
    attempt = await service.owned(db, LearningAttempt, attempt_id, owner.id)
    if attempt.item_id != identifier or attempt.kind != "practice":
        fail(404, "attempt_missing", "Practice attempt was not found for this item.")
    return await submit_answer(attempt.interview_id, payload, actor, db)


@router.post("/learning/retries", dependencies=mutation, status_code=201)
async def retry(payload: RetryInput, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    attempt = await service.retry(db, owner.id, payload)
    await db.commit()
    return await service.attempt_value(db, attempt)


@router.post("/knowledge-gaps/{identifier}/retry", dependencies=mutation, status_code=201)
async def gap_retry(identifier: UUID, payload: PracticeInput, actor: CandidateActor, db: DB):
    return await retry(
        RetryInput(mode="single", gap_ids=[identifier], idempotency_key=payload.idempotency_key),
        actor,
        db,
    )


@router.get("/candidates/me/progress")
async def progress(actor: CandidateActor, db: DB, job_id: UUID | None = None):
    owner = await candidate(db, actor.user.id)
    return await service.progress(db, owner.id, job_id)
