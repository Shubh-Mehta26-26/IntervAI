"""Small durable PostgreSQL queue; no in-process request background tasks."""

import asyncio
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, or_, select
from starlette.concurrency import run_in_threadpool

from app.db.session import SessionFactory, engine
from app.models.intelligence import Resume, ResumeSkill
from app.models.interviews import Interview, InterviewJob
from app.providers.documents import DocumentError, IsolatedDocumentExtractor
from app.providers.embeddings import EmbeddingError, get_embedding_provider
from app.providers.llm import LLMError, get_provider
from app.providers.parsing import PARSER_VERSION, DeterministicResumeParser
from app.providers.storage import storage
from app.services.intelligence import skill_id
from app.services.interviews import process_interview_job
from app.services.voice import AudioStorage, process_speech_job


async def process_resume_one(factory=SessionFactory):
    now = datetime.now(timezone.utc)
    async with factory() as db:
        row = await db.scalar(
            select(Resume)
            .where(
                or_(
                    Resume.status == "uploaded",
                    (Resume.status == "processing") & (Resume.lease_until < now),
                )
            )
            .order_by(Resume.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        if row.attempts >= 3:
            row.status = row.parsing_status = "failed"
            row.error = "Processing was interrupted repeatedly. Retry this document."
            row.lease_until = None
            await db.commit()
            return True
        row.status = row.parsing_status = "processing"
        row.claim_id = uuid4()
        row.lease_until = now + timedelta(seconds=90)
        row.attempts += 1
        identifier, claim, key = row.id, row.claim_id, row.storage_key
        await db.commit()
    text, parsed, error = None, None, None
    try:
        text = await run_in_threadpool(IsolatedDocumentExtractor().extract, storage().path(key))
        parsed = DeterministicResumeParser().parse(text, f"resume:{identifier}")
    except DocumentError as exc:
        error = str(exc)
    except Exception:
        error = "Document processing failed. Try again or upload a new export."
        logging.getLogger(__name__).error("Resume processing failed: %s", identifier)
    async with factory() as db:
        row = await db.scalar(
            select(Resume)
            .where(Resume.id == identifier, Resume.claim_id == claim)
            .with_for_update()
        )
        if row is None:  # Deleted, replaced claim or retried: stale work cannot write.
            return True
        row.extracted_text = text
        row.error = error
        row.lease_until = None
        if error:
            row.status = row.parsing_status = "failed"
        else:
            await db.execute(delete(ResumeSkill).where(ResumeSkill.resume_id == row.id))
            for item in parsed.skills:
                key = await skill_id(db, item)
                db.add(
                    ResumeSkill(
                        resume_id=row.id,
                        skill_id=key,
                        evidence=[e.model_dump() for e in item.evidence],
                    )
                )
            row.parsed_data = parsed.model_dump()
            row.parser_version = PARSER_VERSION
            row.status = row.parsing_status = "parsed"
        await db.commit()
    return True


async def process_interview_one(factory=SessionFactory, provider=None, embedding_provider=None, stt=None, tts=None, execution=None):
    now = datetime.now(timezone.utc)
    async with factory() as db:
        job = await db.scalar(
            select(InterviewJob)
            .where(
                InterviewJob.available_at <= now,
                or_(
                    InterviewJob.status == "queued",
                    (InterviewJob.status == "running") & (InterviewJob.lease_until < now),
                ),
            )
            .order_by(InterviewJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        if job.attempts >= job.max_attempts and job.kind not in {"stt", "tts"}:
            job.status, job.error_code = "failed", "retry_exhausted"
            job.error_message = "The interview operation was interrupted repeatedly."
            interview = await db.get(Interview, job.interview_id)
            if job.kind == "coding":
                from app.models.coding import CodingSubmission
                row = await db.scalar(select(CodingSubmission).where(CodingSubmission.job_id == job.id))
                if row and row.execution_status != "CANCELLED":
                    row.execution_status, row.status = "SYSTEM_ERROR", "ERROR"
            if interview and interview.revision == job.expected_revision and job.kind not in {"coding", "coding_validate"}:
                interview.status, interview.error_code, interview.error_message = (
                    "failed",
                    job.error_code,
                    job.error_message,
                )
                interview.revision += 1
            await db.commit()
            return True
        job.status, job.claim_id = "running", uuid4()
        job.lease_until, job.attempts = now + timedelta(minutes=3), job.attempts + 1
        if job.kind == "coding_validate":
            job.lease_until = now + timedelta(minutes=5)
        identifier, claim, kind = job.id, job.claim_id, job.kind
        await db.commit()
    if kind in {"stt", "tts"}:
        await process_speech_job(factory, identifier, claim, stt, tts)
        return True
    try:
        if kind in {"coding", "coding_validate"}:
            from app.services.coding import process_coding_job
            await process_coding_job(factory, identifier, claim, execution)
            return True
        await process_interview_job(
            factory,
            identifier,
            claim,
            provider or get_provider(),
            embedding_provider or get_embedding_provider(),
        )
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, (LLMError, EmbeddingError))
            else "interview_processing_failed"
        )
        message = (
            str(exc)
            if isinstance(exc, (LLMError, EmbeddingError))
            else "The interview operation failed. Try again."
        )
        logging.getLogger(__name__).error("Interview operation failed: %s (%s)", identifier, code)
        async with factory() as db:
            job = await db.scalar(
                select(InterviewJob)
                .where(InterviewJob.id == identifier, InterviewJob.claim_id == claim)
                .with_for_update()
            )
            if job:
                job.error_code, job.error_message, job.lease_until = code, message[:500], None
                if job.attempts >= job.max_attempts or code in {
                    "llm_not_configured",
                    "embedding_not_configured",
                }:
                    job.status = "failed"
                    interview = await db.get(Interview, job.interview_id)
                    if kind == "coding":
                        from app.models.coding import CodingSubmission
                        row = await db.scalar(select(CodingSubmission).where(CodingSubmission.job_id == job.id))
                        if row and row.execution_status != "CANCELLED":
                            row.execution_status, row.status = "SYSTEM_ERROR", "ERROR"
                    if interview and interview.revision == job.expected_revision and kind not in {"coding", "coding_validate"}:
                        interview.status, interview.error_code, interview.error_message = (
                            "failed",
                            code,
                            message[:500],
                        )
                        interview.revision += 1
                else:
                    job.status = "queued"
                    job.available_at = datetime.now(timezone.utc) + timedelta(
                        seconds=60 if code == "embedding_rate_limited" else 2**job.attempts
                    )
                await db.commit()
    return True


async def process_one(factory=SessionFactory, provider=None):
    if await process_resume_one(factory):
        return True
    return await process_interview_one(factory, provider)


async def update_heartbeat(factory=SessionFactory):
    from sqlalchemy.dialects.postgresql import insert

    from app.models.reporting import WorkerHeartbeat

    statement = insert(WorkerHeartbeat).values(
        service="intervai-worker",
        last_seen_at=datetime.now(timezone.utc),
        status="running",
    ).on_conflict_do_update(
        index_elements=[WorkerHeartbeat.service],
        set_={"last_seen_at": datetime.now(timezone.utc), "status": "running"},
    )
    async with factory() as db:
        await db.execute(statement)
        await db.commit()


async def heartbeat_loop():
    logger = logging.getLogger(__name__)
    while True:
        try:
            await update_heartbeat()
        except Exception:
            logger.error("Worker heartbeat update failed")
        await asyncio.sleep(8)


async def main():
    heartbeat = asyncio.create_task(heartbeat_loop())
    try:
        while True:
            try:
                worked = await process_one()
                AudioStorage().sweep()
                from app.services.vision import sweep_sessions
                await sweep_sessions(SessionFactory)
                (Path(tempfile.gettempdir()) / "intervai-worker").touch()
            except Exception:
                logging.getLogger(__name__).error("Worker database operation failed; retrying")
                worked = False
            if not worked:
                await asyncio.sleep(2)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
