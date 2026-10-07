from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.core.errors import fail
from app.models.intelligence import CandidateJobMatch, JobDescription, JobSkill, Resume, Skill
from app.providers.storage import storage
from app.schemas.intelligence import JobInput, JobOut, JobPatch, MatchInput, MatchOut, ResumeOut
from app.services import intelligence as service

router = APIRouter(tags=["intelligence"])
mutation = [Depends(csrf_actor)]


@router.get("/resumes", response_model=list[ResumeOut])
async def resumes(actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    return (
        await db.scalars(
            select(Resume).where(Resume.candidate_id == owner.id).order_by(Resume.version.desc())
        )
    ).all()


@router.post("/resumes", status_code=202, response_model=ResumeOut, dependencies=mutation)
async def upload(actor: CandidateActor, db: DB, file: Annotated[UploadFile, File()]):
    return await service.upload_resume(db, actor.user.id, file)


@router.get("/resumes/{identifier}", response_model=ResumeOut)
async def resume(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    return await service.owned(db, Resume, identifier, owner.id)


@router.get("/resumes/{identifier}/file")
async def download(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, Resume, identifier, owner.id)
    path = storage().path(row.storage_key)
    if not path.is_file():
        fail(404, "file_missing", "Stored document is unavailable. Upload a replacement.")
    return FileResponse(
        path,
        media_type=row.media_type,
        filename=row.original_name,
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/resumes/{identifier}/replace",
    status_code=202,
    response_model=ResumeOut,
    dependencies=mutation,
)
async def replace(
    identifier: UUID, actor: CandidateActor, db: DB, file: Annotated[UploadFile, File()]
):
    # Replacement is a new historical version; old evidence remains until explicitly deleted.
    return await service.upload_resume(db, actor.user.id, file, replace_id=identifier)


@router.post(
    "/resumes/{identifier}/retry", status_code=202, response_model=ResumeOut, dependencies=mutation
)
async def retry(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, Resume, identifier, owner.id, lock=True)
    if row.status != "failed":
        fail(409, "invalid_state", "Only failed documents need a retry.")
    row.status, row.parsing_status, row.error, row.attempts = "uploaded", "pending", None, 0
    row.claim_id = None
    await db.commit()
    return row


@router.delete("/resumes/{identifier}", status_code=204, dependencies=mutation)
async def remove_resume(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id, lock=True)
    row = await service.owned(db, Resume, identifier, owner.id, lock=True)
    await service.delete_resume(db, row)
    return Response(status_code=204)


@router.get("/jobs", response_model=list[JobOut])
async def jobs(actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    return (
        await db.scalars(
            select(JobDescription)
            .where(JobDescription.candidate_id == owner.id)
            .order_by(JobDescription.updated_at.desc())
        )
    ).all()


@router.post("/jobs", status_code=201, response_model=JobOut, dependencies=mutation)
async def create_job(payload: JobInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id, lock=True)
    count = await db.scalar(
        select(func.count())
        .select_from(JobDescription)
        .where(JobDescription.candidate_id == owner.id)
    )
    if count >= 100:
        fail(409, "job_limit", "Keep at most 100 job targets. Delete an old target first.")
    row = JobDescription(candidate_id=owner.id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return row


@router.get("/jobs/{identifier}", response_model=JobOut)
async def job(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    return await service.owned(db, JobDescription, identifier, owner.id)


@router.patch("/jobs/{identifier}", response_model=JobOut, dependencies=mutation)
async def update_job(identifier: UUID, payload: JobPatch, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, JobDescription, identifier, owner.id, lock=True)
    if row.version != payload.expected_version:
        fail(409, "revision_conflict", "This job changed. Reload before saving.")
    for key, value in payload.model_dump(exclude={"expected_version"}).items():
        setattr(row, key, value)
    row.version += 1
    row.analysis, row.analyzed_version, row.status = None, None, "draft"
    await db.execute(delete(JobSkill).where(JobSkill.job_id == row.id))
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/jobs/{identifier}", status_code=204, dependencies=mutation)
async def remove_job(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, JobDescription, identifier, owner.id, lock=True)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.post("/jobs/{identifier}/analyze", response_model=JobOut, dependencies=mutation)
async def analyze_job(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, JobDescription, identifier, owner.id, lock=True)
    return await service.analyze(db, row)


@router.post("/jobs/{identifier}/match", response_model=MatchOut, dependencies=mutation)
async def match_job(identifier: UUID, payload: MatchInput, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id, lock=True)
    row = await service.owned(db, JobDescription, identifier, owner.id, lock=True)
    return await service.match_job(db, row, owner, payload.resume_id)


@router.get("/jobs/{identifier}/match", response_model=MatchOut)
async def get_match(identifier: UUID, actor: CandidateActor, db: DB):
    owner = await service.candidate(db, actor.user.id)
    row = await service.owned(db, JobDescription, identifier, owner.id)
    match = await db.scalar(select(CandidateJobMatch).where(CandidateJobMatch.job_id == row.id))
    if match is None:
        fail(404, "match_missing", "No saved match yet. Analyze this job and run a match.")
    return await service.match_out(db, match, row, owner)


@router.get("/skills")
async def skills(actor: CandidateActor, db: DB, query: str = Query(default="", max_length=100)):
    rows = (
        await db.scalars(
            select(Skill).where(Skill.name.ilike("%" + query + "%")).order_by(Skill.name).limit(100)
        )
    ).all()
    return [
        {"id": row.id, "name": row.name, "category": row.category, "slug": row.slug} for row in rows
    ]
