import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.core.errors import fail
from app.models.intelligence import JobDescription, Resume
from app.models.interviews import (
    AdaptiveDecision,
    AnswerEvaluation,
    Interview,
    InterviewAnswer,
    InterviewJob,
    InterviewQuestion,
)
from app.providers.embeddings import embedding_status
from app.providers.llm import provider_status
from app.schemas.interviews import (
    AnswerInput,
    AnswerOut,
    InterviewCreate,
    InterviewOut,
    OperationOut,
    ProviderStatus,
    QuestionOut,
    StartInput,
    TransitionInput,
)
from app.services import interviews as service
from app.services.memory import CandidateMemoryService

router = APIRouter(prefix="/interviews", tags=["interviews"])
mutation = [Depends(csrf_actor)]


def require_llm_ready():
    ready, _provider, _model, message = provider_status()
    if not ready:
        fail(503, "llm_not_configured", message)
    embedding_ready, _provider, _model, message = embedding_status()
    if not embedding_ready:
        fail(503, "embedding_not_configured", message)


@router.get("/provider", response_model=ProviderStatus)
async def llm_status(actor: CandidateActor):
    ready, provider, model, message = provider_status()
    embedding_ready, _, _, embedding_message = embedding_status()
    if ready and not embedding_ready:
        ready, message = False, embedding_message
    elif not ready and not embedding_ready:
        message = message + " " + embedding_message
    return ProviderStatus(configured=ready, provider=provider, model=model, message=message)


@router.post("", status_code=201, response_model=InterviewOut, dependencies=mutation)
async def create(payload: InterviewCreate, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    if payload.job_id:
        job = await db.scalar(
            select(JobDescription).where(
                JobDescription.id == payload.job_id, JobDescription.candidate_id == owner.id
            )
        )
        if job is None:
            fail(404, "job_missing", "Job target was not found.")
    if payload.resume_id:
        resume = await db.scalar(
            select(Resume).where(Resume.id == payload.resume_id, Resume.candidate_id == owner.id)
        )
        if resume is None:
            fail(404, "resume_missing", "Resume was not found.")
        if resume.status != "parsed":
            fail(409, "resume_not_ready", "Choose a resume that finished processing.")
    config = payload.model_dump(
        mode="json",
        exclude={
            "job_id",
            "resume_id",
            "question_limit",
            "duration_minutes",
            "interview_type",
            "mode",
        },
    )
    row = Interview(
        candidate_id=owner.id,
        job_id=payload.job_id,
        resume_id=payload.resume_id,
        interview_type=payload.interview_type,
        mode=payload.mode,
        question_limit=payload.question_limit,
        duration_minutes=payload.duration_minutes,
        configuration=config,
    )
    db.add(row)
    if row.interview_type == "coding":
        from app.models.coding import CodingProblem
        from app.services.coding import problem_owned, queue_validation
        from app.services.coding_catalog import ensure_catalog
        await db.flush()
        await ensure_catalog(db)
        if payload.coding_problem_ids:
            problem_rows = [await problem_owned(db, key, owner.id) for key in payload.coding_problem_ids]
        else:
            problem_rows = (await db.scalars(select(CodingProblem).where(CodingProblem.candidate_id.is_(None)))).all()
        for problem in problem_rows:
            await queue_validation(db, problem, row)
    await db.commit()
    await db.refresh(row)
    return await service.output(db, row)


@router.get("", response_model=list[InterviewOut])
async def history(
    actor: CandidateActor, db: DB, status: str | None = Query(default=None, max_length=24)
):
    owner = await service.candidate(db, actor.user.id)
    statement = select(Interview).where(Interview.candidate_id == owner.id)
    if status:
        statement = statement.where(Interview.status == status)
    rows = (await db.scalars(statement.order_by(Interview.created_at.desc()).limit(100))).all()
    return [await service.output(db, row) for row in rows]


@router.get("/{identifier}", response_model=InterviewOut)
async def detail(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    return await service.output(db, await service.owned(db, identifier, owner.id))


@router.get("/{identifier}/current", response_model=InterviewOut)
async def current(identifier: UUID, actor: CandidateActor, db: DB):
    return await detail(identifier, actor, db)


@router.post(
    "/{identifier}/start",
    status_code=202,
    response_model=OperationOut,
    dependencies=[Depends(csrf_actor), Depends(require_llm_ready)],
)
async def start(identifier: UUID, payload: StartInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    service.check_revision(row, payload.expected_revision)
    if row.status != "created":
        fail(409, "invalid_state", "Only a newly created interview can be started.")
    row.status, row.revision = "planning", row.revision + 1
    job = InterviewJob(
        interview_id=row.id,
        kind="plan",
        dedupe_key=f"plan:{row.id}",
        expected_revision=row.revision,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return OperationOut(
        interview_id=row.id, operation_id=job.id, status=job.status, revision=row.revision
    )


@router.get("/{identifier}/questions", response_model=list[QuestionOut])
async def questions(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id)
    return (
        await db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.interview_id == row.id)
            .order_by(InterviewQuestion.sequence)
        )
    ).all()


@router.get("/{identifier}/answers", response_model=list[AnswerOut])
async def answers(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id)
    result = []
    answer_rows = (
        await db.scalars(
            select(InterviewAnswer)
            .where(InterviewAnswer.interview_id == row.id)
            .order_by(InterviewAnswer.sequence)
        )
    ).all()
    reveal = row.mode == "practice" or row.status == "completed"
    for answer in answer_rows:
        evaluation = (
            await db.scalar(select(AnswerEvaluation).where(AnswerEvaluation.answer_id == answer.id))
            if reveal
            else None
        )
        decision = (
            await db.scalar(
                select(AdaptiveDecision).where(AdaptiveDecision.evaluation_id == evaluation.id)
            )
            if evaluation
            else None
        )
        evaluation_value = await service.evaluation_output(db, evaluation) if evaluation else None
        result.append(
            AnswerOut.model_validate(
                {**answer.__dict__, "evaluation": evaluation_value, "decision": decision}
            )
        )
    return result


@router.post(
    "/{identifier}/answers",
    status_code=202,
    response_model=OperationOut,
    dependencies=[Depends(csrf_actor), Depends(require_llm_ready)],
)
async def submit_answer(identifier: UUID, payload: AnswerInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    if row.interview_type == "coding":
        fail(409, "coding_submission_required", "Run or submit code in the coding editor.")
    fingerprint = service.answer_hash(payload.question_id, payload.text, payload.duration_seconds)
    if payload.voice_turn_id:
        fingerprint = hashlib.sha256((fingerprint + str(payload.voice_turn_id)).encode()).hexdigest()
    duplicate = await db.scalar(
        select(InterviewAnswer).where(
            InterviewAnswer.interview_id == row.id,
            InterviewAnswer.idempotency_key == payload.idempotency_key,
        )
    )
    if duplicate:
        if duplicate.payload_hash != fingerprint:
            fail(
                409,
                "idempotency_conflict",
                "This request key was already used for a different answer.",
            )
        job = await db.scalar(select(InterviewJob).where(InterviewJob.answer_id == duplicate.id))
        return OperationOut(
            interview_id=row.id, operation_id=job.id, status=job.status, revision=row.revision
        )
    service.check_revision(row, payload.expected_revision)
    if row.status != "waiting_for_answer":
        fail(409, "invalid_state", "This interview is not waiting for an answer.")
    question = await db.scalar(
        select(InterviewQuestion)
        .where(
            InterviewQuestion.id == payload.question_id,
            InterviewQuestion.interview_id == row.id,
            InterviewQuestion.sequence == row.current_question,
        )
        .with_for_update()
    )
    if question is None or question.state != "waiting":
        fail(409, "question_not_current", "Reload to answer the current question.")
    answer = InterviewAnswer(
        interview_id=row.id,
        question_id=question.id,
        candidate_id=owner.id,
        sequence=question.sequence,
        text=payload.text,
        duration_seconds=payload.duration_seconds,
        idempotency_key=payload.idempotency_key,
        payload_hash=fingerprint,
    )
    db.add(answer)
    await db.flush()
    from app.services.voice import link_answer
    await link_answer(db, row, payload, answer)
    row.status, row.revision = "evaluating", row.revision + 1
    job = InterviewJob(
        interview_id=row.id,
        answer_id=answer.id,
        kind="answer",
        dedupe_key=f"answer:{answer.id}",
        expected_revision=row.revision,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return OperationOut(
        interview_id=row.id, operation_id=job.id, status=job.status, revision=row.revision
    )


@router.post("/{identifier}/pause", response_model=InterviewOut, dependencies=mutation)
async def pause(identifier: UUID, payload: TransitionInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    service.check_revision(row, payload.expected_revision)
    if row.status != "waiting_for_answer":
        fail(409, "invalid_state", "Pause is available while waiting for an answer.")
    row.status, row.paused_at, row.revision = "paused", datetime.now(timezone.utc), row.revision + 1
    await db.commit()
    return await service.output(db, row)


@router.post("/{identifier}/resume", response_model=InterviewOut, dependencies=mutation)
async def resume(identifier: UUID, payload: TransitionInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    service.check_revision(row, payload.expected_revision)
    if row.status != "paused":
        fail(409, "invalid_state", "Only a paused interview can resume.")
    row.status, row.paused_at, row.revision = "waiting_for_answer", None, row.revision + 1
    await db.commit()
    return await service.output(db, row)


@router.post("/{identifier}/complete", response_model=InterviewOut, dependencies=mutation)
async def complete(identifier: UUID, payload: TransitionInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    service.check_revision(row, payload.expected_revision)
    if row.status not in {"waiting_for_answer", "paused"}:
        fail(409, "invalid_state", "This interview cannot be completed from its current state.")
    row.status, row.completed_at, row.revision = (
        "completed",
        datetime.now(timezone.utc),
        row.revision + 1,
    )
    row.summary = await service.build_summary(db, row.id)
    await db.flush()
    await CandidateMemoryService.complete_interview(db, row.id)
    from app.services.learning import record_comparison
    await record_comparison(db, row)
    await db.commit()
    return await service.output(db, row)


@router.post("/{identifier}/cancel", response_model=InterviewOut, dependencies=mutation)
async def cancel(identifier: UUID, payload: TransitionInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id, lock=True)
    service.check_revision(row, payload.expected_revision)
    if row.status in {"completed", "cancelled"}:
        fail(409, "invalid_state", "This interview has already ended.")
    row.status, row.completed_at, row.revision = (
        "cancelled",
        datetime.now(timezone.utc),
        row.revision + 1,
    )
    jobs = (
        await db.scalars(
            select(InterviewJob).where(
                InterviewJob.interview_id == row.id, InterviewJob.status.in_(["queued", "running"])
            )
        )
    ).all()
    for job in jobs:
        job.status = "cancelled"
    await db.commit()
    return await service.output(db, row)


@router.get("/{identifier}/summary")
async def summary(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, identifier, owner.id)
    if row.status != "completed":
        fail(409, "interview_incomplete", "Complete the interview before viewing its summary.")
    return row.summary
