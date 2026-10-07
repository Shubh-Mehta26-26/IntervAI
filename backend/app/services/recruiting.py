from datetime import datetime, timezone

from sqlalchemy import select

from app.core.errors import fail
from app.models.identity import Candidate, Experience, User
from app.models.intelligence import CandidateJobMatch, JobDescription, Resume, ResumeSkill, Skill
from app.models.recruiting import RecruiterApplication, RecruiterJob

CONSENT_VERSION = 1


def job_value(row):
    return {
        "id": str(row.id),
        "title": row.title,
        "company": row.company,
        "description": row.description,
        "status": row.status,
        "version": row.version,
        "requirements": row.requirements,
        "created_at": row.created_at.isoformat(),
        "applicant_count": None,
    }


async def owned_job(db, recruiter_id, job_id, *, lock=False):
    query = select(RecruiterJob).where(
        RecruiterJob.id == job_id,
        RecruiterJob.recruiter_user_id == recruiter_id,
    )
    if lock:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None:
        fail(404, "recruiter_job_missing", "The job was not found.")
    return row


async def owned_application(db, recruiter_id, application_id, *, active_only=True):
    query = select(RecruiterApplication).where(
        RecruiterApplication.id == application_id,
        RecruiterApplication.recruiter_user_id == recruiter_id,
    )
    if active_only:
        query = query.where(RecruiterApplication.status == "applied")
    row = await db.scalar(query)
    if row is None:
        fail(404, "application_missing", "The application was not found.")
    return row


async def apply(db, candidate_id, payload):
    job = await db.get(RecruiterJob, payload.recruiter_job_id)
    candidate_job = await db.scalar(
        select(JobDescription).where(
            JobDescription.id == payload.candidate_job_id,
            JobDescription.candidate_id == candidate_id,
        )
    )
    if job is None or candidate_job is None:
        fail(404, "application_source_missing", "The job or your analyzed job copy was not found.")
    if job.status != "active":
        fail(409, "recruiter_job_unavailable", "This job is not accepting applications.")
    if candidate_job.status != "analyzed" or candidate_job.analyzed_version != candidate_job.version:
        fail(409, "candidate_job_unanalyzed", "Analyze your copy of this job before applying.")
    def normalize(value):
        return " ".join(value.casefold().split())
    if normalize(job.description) != normalize(candidate_job.description):
        fail(
            409,
            "application_job_version_mismatch",
            "Your analyzed job copy does not match this posting. Add the current description as a job target and analyze it first.",
        )
    existing = await db.scalar(
        select(RecruiterApplication).where(
            RecruiterApplication.candidate_id == candidate_id,
            RecruiterApplication.recruiter_job_id == job.id,
        )
    )
    if existing and existing.status == "applied":
        return existing
    if existing:
        existing.status = "applied"
        existing.candidate_job_id = candidate_job.id
        existing.consented_at = datetime.now(timezone.utc)
        existing.consent_version = CONSENT_VERSION
        await db.commit()
        await db.refresh(existing)
        return existing
    row = RecruiterApplication(
        recruiter_user_id=job.recruiter_user_id,
        recruiter_job_id=job.id,
        candidate_id=candidate_id,
        candidate_job_id=candidate_job.id,
        status="applied",
        consented_at=datetime.now(timezone.utc),
        consent_version=CONSENT_VERSION,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def candidate_application_value(db, row):
    job = await db.get(RecruiterJob, row.recruiter_job_id)
    return {
        "id": str(row.id),
        "job_id": str(row.recruiter_job_id),
        "title": job.title if job else "Closed job",
        "company": job.company if job else "",
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


async def application_detail(db, row):
    user, candidate, candidate_job = (
        await db.execute(
            select(User, Candidate, JobDescription)
            .join(Candidate, Candidate.user_id == User.id)
            .join(JobDescription, JobDescription.id == row.candidate_job_id)
            .where(Candidate.id == row.candidate_id)
        )
    ).one()
    job = await db.get(RecruiterJob, row.recruiter_job_id)
    match = await db.scalar(
        select(CandidateJobMatch).where(CandidateJobMatch.job_id == candidate_job.id)
    )
    resume = await db.get(Resume, match.resume_id) if match and match.resume_id else None
    skills = []
    if resume:
        rows = (
            await db.execute(
                select(Skill, ResumeSkill)
                .join(ResumeSkill, ResumeSkill.skill_id == Skill.id)
                .where(ResumeSkill.resume_id == resume.id)
                .order_by(Skill.name)
            )
        ).all()
        skills = [
            {
                "skill": skill.name,
                "evidence": [
                    {"quote": str(item.get("quote", ""))[:300], "line": item.get("line")}
                    for item in (resume_skill.evidence or [])[:3]
                ],
            }
            for skill, resume_skill in rows
        ]
    experience = (
        await db.scalars(
            select(Experience)
            .where(Experience.candidate_id == candidate.id)
            .order_by(Experience.id)
            .limit(20)
        )
    ).all()
    from app.models.interviews import Interview
    from app.models.reporting import Report, ReportVersion

    report_rows = (
        await db.execute(
            select(Interview, Report, ReportVersion)
            .join(Report, Report.interview_id == Interview.id)
            .join(ReportVersion, ReportVersion.report_id == Report.id)
            .where(
                Interview.candidate_id == candidate.id,
                Interview.job_id == candidate_job.id,
                Interview.status == "completed",
                Report.candidate_id == candidate.id,
                ReportVersion.version == Report.latest_version,
            )
            .order_by(Interview.completed_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "id": str(row.id),
        "status": row.status,
        "consented_at": row.consented_at.isoformat(),
        "consent_version": row.consent_version,
        "job": {"id": str(job.id), "title": job.title, "company": job.company},
        "candidate": {
            "id": str(candidate.id),
            "display_name": user.display_name,
            "email": user.email,
            "headline": candidate.headline,
            "experience_months": candidate.experience_months,
            "resume_version": resume.version if resume else None,
            "resume_skills": skills,
            "experience": [
                {"title": item.title, "description": (item.description or "")[:600]}
                for item in experience
            ],
        },
        "job_match": match.result if match else None,
        "reports": [
            {
                "id": str(report.id),
                "interview_id": str(interview.id),
                "version": version.version,
                "generated_at": version.generated_at.isoformat(),
                "interview_type": interview.interview_type,
            }
            for interview, report, version in report_rows
        ],
        "scope_note": "This review is limited to the candidate's consented application, matching job copy, related resume/job match, and completed interviews linked to that job.",
    }
