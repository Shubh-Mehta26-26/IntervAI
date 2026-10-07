import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.core.errors import fail
from app.models.identity import Candidate, Experience
from app.models.intelligence import CandidateJobMatch, JobSkill, Resume, Skill
from app.providers.documents import DocumentError, validate_container
from app.providers.parsing import PARSER_VERSION, analyze_job, extract_skills, lines
from app.providers.storage import MAX_FILE_BYTES, storage
from app.schemas.intelligence import MatchOut, MatchResult, MatchSkill, ResumeFacts


async def candidate(db, user_id, lock=False):
    statement = select(Candidate).where(Candidate.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        fail(404, "not_found", "Candidate profile not found.")
    return row


async def owned(db, model, identifier, candidate_id, lock=False):
    statement = select(model).where(model.id == identifier, model.candidate_id == candidate_id)
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        fail(404, "not_found", "This item was not found.")
    return row


async def skill_id(db, value):
    statement = insert(Skill).values(slug=value.slug, name=value.name, category=value.category)
    await db.execute(statement.on_conflict_do_nothing(index_elements=["slug"]))
    return await db.scalar(select(Skill.id).where(Skill.slug == value.slug))


async def upload_resume(db, user_id, upload, replace_id=None):
    owner = await candidate(db, user_id, lock=True)
    if replace_id:
        await owned(db, Resume, replace_id, owner.id)
    count = await db.scalar(
        select(func.count()).select_from(Resume).where(Resume.candidate_id == owner.id)
    )
    if count >= 20:
        fail(409, "resume_limit", "Keep at most 20 resume versions. Delete an old version first.")
    filename = (upload.filename or "document").replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^\w .()+-]", "_", filename)[:200]
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        fail(415, "unsupported_file", "Upload a PDF or DOCX document.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    await upload.close()
    if not data or len(data) > MAX_FILE_BYTES:
        fail(413, "file_size", "Choose a non-empty file of at most 10 MB.")
    try:
        await run_in_threadpool(validate_container, data, suffix)
    except DocumentError as exc:
        fail(422, "invalid_document", str(exc))
    checksum = hashlib.sha256(data).hexdigest()
    existing = await db.scalar(
        select(Resume)
        .where(Resume.candidate_id == owner.id, Resume.sha256 == checksum)
        .order_by(Resume.version.desc())
    )
    if existing:
        return existing
    version = (
        await db.scalar(select(func.max(Resume.version)).where(Resume.candidate_id == owner.id))
        or 0
    ) + 1
    store = storage()
    key = await run_in_threadpool(store.put, data, suffix)
    resume = Resume(
        candidate_id=owner.id,
        original_name=filename,
        media_type="application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=len(data),
        storage_key=key,
        sha256=checksum,
        version=version,
    )
    db.add(resume)
    try:
        await db.commit()
    except Exception:
        await run_in_threadpool(store.delete, key)
        raise
    return resume


async def delete_resume(db, resume):
    # File deletion precedes row removal: errors retain the DB record for a safe retry.
    await run_in_threadpool(storage().delete, resume.storage_key)
    await db.delete(resume)
    await db.commit()


async def analyze(db, job):
    if job.analyzed_version == job.version and job.analysis:
        return job
    analysis = analyze_job(job.description)
    await db.execute(delete(JobSkill).where(JobSkill.job_id == job.id))
    for item in analysis.skills:
        key = await skill_id(db, item)
        db.add(
            JobSkill(
                job_id=job.id,
                skill_id=key,
                requirement=item.requirement,
                evidence=[e.model_dump() for e in item.evidence],
            )
        )
    job.analysis = analysis.model_dump()
    job.analyzed_version = job.version
    job.status = "analyzed"
    await db.commit()
    await db.refresh(job)
    return job


def fingerprint(job, profile, resume):
    return hashlib.sha256(
        json.dumps(
            {
                "job": job.version,
                "profile": profile.revision,
                "resume": str(resume.id) if resume else None,
                "hash": resume.sha256 if resume else None,
                "parser": resume.parser_version if resume else None,
                "policy": PARSER_VERSION,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def match_out(db, match, job, profile):
    resume = await db.get(Resume, match.resume_id) if match.resume_id else None
    return MatchOut(
        id=match.id,
        resume_id=match.resume_id,
        created_at=match.updated_at,
        stale=match.fingerprint != fingerprint(job, profile, resume),
        result=MatchResult.model_validate(match.result),
    )


async def match_job(db, job, profile, resume_id):
    if job.analyzed_version != job.version or not job.analysis:
        fail(409, "analysis_required", "Analyze the current job description before matching.")
    resume = await owned(db, Resume, resume_id, profile.id) if resume_id else None
    if resume and resume.status != "parsed":
        fail(409, "resume_not_ready", "Wait for the selected resume to finish parsing.")
    current = await db.scalar(select(CandidateJobMatch).where(CandidateJobMatch.job_id == job.id))
    stamp = fingerprint(job, profile, resume)
    if current and current.fingerprint == stamp:
        return await match_out(db, current, job, profile)
    # Profile narrative and work records are candidate statements, never inferred from interests/goals.
    profile_text = "\n".join(
        ["Summary", profile.headline or "", profile.biography or "", "Experience"]
    )
    work = (
        await db.scalars(
            select(Experience)
            .where(Experience.candidate_id == profile.id)
            .order_by(Experience.created_at, Experience.id)
        )
    ).all()
    profile_text += "\n" + "\n".join(
        f"{item.title} at {item.organization}: {item.description or ''}" for item in work
    )
    evidence_skills = extract_skills(list(lines(profile_text, "profile")))
    if resume:
        evidence_skills += ResumeFacts.model_validate(resume.parsed_data).skills
    grouped = {}
    for item in evidence_skills:
        grouped.setdefault(item.slug, []).extend(item.evidence)
    results = []
    for requirement in job.analysis["skills"]:
        item = next(
            (
                value
                for value in (
                    await db.scalars(select(Skill).where(Skill.slug == requirement["slug"]))
                ).all()
            ),
            None,
        )
        evidence = grouped.get(requirement["slug"], [])[:16]
        status = (
            "demonstrated"
            if any(entry.kind == "applied" for entry in evidence)
            else "partial"
            if evidence
            else "not_demonstrated"
        )
        reason = {
            "demonstrated": "An explicit use claim appears in work/project evidence; proficiency remains unassessed.",
            "partial": "The skill is mentioned, but no explicit work/project use was extracted.",
            "not_demonstrated": "No matching evidence was found in the selected resume or current profile. This does not prove the skill is absent.",
        }[status]
        results.append(
            MatchSkill(
                skill_id=item.id,
                name=item.name,
                category=item.category,
                requirement=requirement["requirement"],
                status=status,
                explanation=reason,
                evidence=evidence,
                job_evidence=requirement["evidence"],
            )
        )
    other = []
    seen = set()
    for section in [
        "experience_requirements",
        "qualifications",
        "responsibilities",
        "other_requirements",
    ]:
        for entry in job.analysis[section]:
            if entry["line"] not in seen:
                other.append(entry)
                seen.add(entry["line"])
    result = MatchResult(
        policy_version=PARSER_VERSION,
        job_version=job.version,
        profile_revision=profile.revision,
        skills=results,
        unassessed_requirements=other,
        explanation="Exact canonical skill matching with cited source text. Applied claims, mentions and no evidence are distinct. No aggregate rating or proficiency score is calculated. Qualifications and experience duration are not automatically verified.",
    )
    if current is None:
        current = CandidateJobMatch(job_id=job.id)
        db.add(current)
    current.resume_id = resume.id if resume else None
    current.fingerprint = stamp
    current.result = result.model_dump(mode="json")
    await db.commit()
    await db.refresh(current)
    return await match_out(db, current, job, profile)
