from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.models.reporting import Report, ReportVersion
from app.services import reporting
from app.services.interviews import candidate

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
async def list_reports(actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    rows = (
        await db.execute(
            select(Report, ReportVersion)
            .join(ReportVersion, ReportVersion.report_id == Report.id)
            .where(Report.candidate_id == owner.id, ReportVersion.version == Report.latest_version)
            .order_by(ReportVersion.generated_at.desc())
            .limit(50)
        )
    ).all()
    return [reporting.output(report, version) for report, version in rows]


@router.post("/{interview_id}/generate", dependencies=[Depends(csrf_actor)])
async def generate(interview_id: UUID, actor: CandidateActor, db: DB):
    owner = await candidate(db, actor.user.id)
    report, version = await reporting.generate(db, owner.id, interview_id)
    return reporting.output(report, version)


@router.get("/{report_id}")
async def get_report(report_id: UUID, actor: CandidateActor, db: DB, version: int | None = None):
    owner = await candidate(db, actor.user.id)
    report = await db.scalar(
        select(Report).where(Report.id == report_id, Report.candidate_id == owner.id)
    )
    if report is None:
        from app.core.errors import fail

        fail(404, "report_missing", "The report was not found.")
    query = select(ReportVersion).where(ReportVersion.report_id == report.id)
    row = await db.scalar(query.where(ReportVersion.version == (version or report.latest_version)))
    if row is None:
        from app.core.errors import fail

        fail(404, "report_version_missing", "The report version was not found.")
    return reporting.output(report, row)


@router.get("/{report_id}/pdf")
async def report_pdf(report_id: UUID, actor: CandidateActor, db: DB, version: int | None = None):
    owner = await candidate(db, actor.user.id)
    report = await db.scalar(
        select(Report).where(Report.id == report_id, Report.candidate_id == owner.id)
    )
    if report is None:
        from app.core.errors import fail

        fail(404, "report_missing", "The report was not found.")
    row = await db.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.version == (version or report.latest_version),
        )
    )
    if row is None:
        from app.core.errors import fail

        fail(404, "report_version_missing", "The report version was not found.")
    return Response(
        content=reporting.make_pdf(row.snapshot, row.version),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="intervai-report-v{row.version}.pdf"'},
    )
