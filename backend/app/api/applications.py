from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, MutationActor
from app.core.errors import fail
from app.models.identity import Candidate
from app.models.recruiting import RecruiterApplication, RecruiterJob
from app.schemas.phase12 import ApplicationInput, ApplicationStatusInput
from app.services import recruiting

router = APIRouter(prefix="/applications", tags=["applications"])


async def candidate_id(db, user_id):
    row = await db.scalar(select(Candidate).where(Candidate.user_id == user_id))
    if row is None:
        fail(404, "candidate_missing", "Candidate profile not found.")
    return row.id


@router.get("/jobs")
async def job_board(db: DB, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000)):
    rows = (await db.scalars(select(RecruiterJob).where(RecruiterJob.status == "active").order_by(RecruiterJob.created_at.desc()).offset(offset).limit(limit))).all()
    return {"items": [recruiting.job_value(row) for row in rows], "limit": limit, "offset": offset}


@router.get("")
async def list_applications(actor: CandidateActor, db: DB):
    owner_id = await candidate_id(db, actor.user.id)
    rows = (await db.scalars(select(RecruiterApplication).where(RecruiterApplication.candidate_id == owner_id).order_by(RecruiterApplication.created_at.desc()).limit(100))).all()
    return [await recruiting.candidate_application_value(db, row) for row in rows]


@router.post("", status_code=201)
async def apply(payload: ApplicationInput, actor: CandidateActor, db: DB, csrf: MutationActor):
    owner_id = await candidate_id(db, actor.user.id)
    row = await recruiting.apply(db, owner_id, payload)
    return await recruiting.candidate_application_value(db, row)


@router.patch("/{application_id}")
async def update_application(application_id: UUID, payload: ApplicationStatusInput, actor: CandidateActor, db: DB, csrf: MutationActor):
    owner_id = await candidate_id(db, actor.user.id)
    row = await db.scalar(select(RecruiterApplication).where(RecruiterApplication.id == application_id, RecruiterApplication.candidate_id == owner_id).with_for_update())
    if row is None:
        fail(404, "application_missing", "The application was not found.")
    row.status = payload.status
    await db.commit()
    await db.refresh(row)
    return await recruiting.candidate_application_value(db, row)
