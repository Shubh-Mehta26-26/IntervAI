from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from app.api.dependencies import DB, MutationActor, RecruiterActor
from app.core.errors import fail
from app.models.identity import Candidate, User
from app.models.interviews import Interview
from app.models.recruiting import RecruiterApplication, RecruiterJob
from app.models.reporting import Report, ReportVersion
from app.schemas.phase12 import RecruiterJobInput, RecruiterJobPatch
from app.services import recruiting, reporting

router = APIRouter(prefix="/recruiter", tags=["recruiter"])


@router.get("/jobs")
async def jobs(actor: RecruiterActor, db: DB):
    rows = (await db.execute(select(RecruiterJob, func.count(RecruiterApplication.id).filter(RecruiterApplication.status == "applied")).outerjoin(RecruiterApplication, RecruiterApplication.recruiter_job_id == RecruiterJob.id).where(RecruiterJob.recruiter_user_id == actor.user.id).group_by(RecruiterJob.id).order_by(RecruiterJob.created_at.desc()).limit(100))).all()
    return [{**recruiting.job_value(job), "applicant_count": count} for job, count in rows]


@router.post("/jobs", status_code=201)
async def create_job(payload: RecruiterJobInput, actor: RecruiterActor, db: DB, csrf: MutationActor):
    row = RecruiterJob(recruiter_user_id=actor.user.id, title=payload.title, company=payload.company, description=payload.description, status="active", version=1, requirements={})
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return recruiting.job_value(row)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: UUID, payload: RecruiterJobPatch, actor: RecruiterActor, db: DB, csrf: MutationActor):
    row = await recruiting.owned_job(db, actor.user.id, job_id, lock=True)
    if row.version != payload.expected_version:
        fail(409, "recruiter_job_revision_conflict", "This job changed in another tab.")
    has_applications = await db.scalar(select(RecruiterApplication.id).where(RecruiterApplication.recruiter_job_id == row.id).limit(1))
    content_changed = any(getattr(payload, name) is not None and getattr(payload, name) != getattr(row, name) for name in ("title", "company", "description"))
    if has_applications and content_changed:
        fail(409, "recruiter_job_has_applicants", "Job content is locked after the first consented application; pause or close the posting instead.")
    for name in ("title", "company", "description", "status"):
        value = getattr(payload, name)
        if value is not None:
            setattr(row, name, value)
    row.version += 1
    await db.commit()
    await db.refresh(row)
    return recruiting.job_value(row)


@router.get("/jobs/{job_id}/applications")
async def applications(job_id: UUID, actor: RecruiterActor, db: DB, status: str = Query(default="applied", pattern="^(applied|withdrawn|closed|all)$"), skill: str | None = Query(default=None, max_length=120), limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000)):
    await recruiting.owned_job(db, actor.user.id, job_id)
    query = select(RecruiterApplication, User, Candidate).join(Candidate, Candidate.id == RecruiterApplication.candidate_id).join(User, User.id == Candidate.user_id).where(RecruiterApplication.recruiter_user_id == actor.user.id, RecruiterApplication.recruiter_job_id == job_id).order_by(RecruiterApplication.created_at.desc())
    if status != "all":
        query = query.where(RecruiterApplication.status == status)
    rows = (await db.execute(query.offset(offset).limit(limit))).all()
    values = []
    for application, user, candidate in rows:
        detail = {"id": str(application.id), "status": application.status, "applied_at": application.created_at.isoformat(), "candidate": {"id": str(candidate.id), "display_name": user.display_name, "headline": candidate.headline}}
        if skill:
            from app.models.intelligence import CandidateJobMatch
            match = await db.scalar(select(CandidateJobMatch).where(CandidateJobMatch.job_id == application.candidate_job_id))
            if not match or skill.casefold() not in str(match.result).casefold():
                continue
        values.append(detail)
    return {"items": values, "limit": limit, "offset": offset, "has_more": len(rows) == limit}


@router.get("/applications/{application_id}")
async def application(application_id: UUID, actor: RecruiterActor, db: DB):
    row = await recruiting.owned_application(db, actor.user.id, application_id)
    return await recruiting.application_detail(db, row)


async def report_for_application(db, application, report_id):
    report = await db.scalar(select(Report).join(Interview, Interview.id == Report.interview_id).where(Report.id == report_id, Report.candidate_id == application.candidate_id, Interview.candidate_id == application.candidate_id, Interview.job_id == application.candidate_job_id))
    if report is None:
        fail(404, "report_missing", "The report is not available in this application scope.")
    version = await db.scalar(select(ReportVersion).where(ReportVersion.report_id == report.id, ReportVersion.version == report.latest_version))
    if version is None:
        fail(404, "report_missing", "The report was not found.")
    return report, version


@router.get("/applications/{application_id}/reports/{report_id}")
async def application_report(application_id: UUID, report_id: UUID, actor: RecruiterActor, db: DB):
    application = await recruiting.owned_application(db, actor.user.id, application_id)
    report, version = await report_for_application(db, application, report_id)
    return reporting.output(report, version)


@router.get("/applications/{application_id}/reports/{report_id}/pdf")
async def application_report_pdf(application_id: UUID, report_id: UUID, actor: RecruiterActor, db: DB):
    application = await recruiting.owned_application(db, actor.user.id, application_id)
    _, version = await report_for_application(db, application, report_id)
    return Response(content=reporting.make_pdf(version.snapshot, version.version), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="intervai-report-v{version.version}.pdf"'})
