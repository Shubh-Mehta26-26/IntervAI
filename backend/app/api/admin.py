from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select, text

from app.api.dependencies import DB, AdminActor, MutationActor
from app.core.errors import fail
from app.models.identity import User
from app.models.recruiting import AdminAudit
from app.models.reporting import WorkerHeartbeat
from app.providers.embeddings import embedding_status
from app.providers.execution import ExecutionProvider
from app.providers.llm import provider_status
from app.providers.speech import speech_status
from app.providers.vision import vision_status
from app.schemas.phase12 import AdminRoleInput

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/system-status")
async def system_status(actor: AdminActor, db: DB):
    from app.db.session import engine
    from app.models.coding import CodingSubmission
    from app.models.interviews import InterviewJob

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        database = "connected"
    except Exception:
        database = "unavailable"
    ready, llm_provider, llm_model, _ = provider_status()
    embedding_ready, embedding_provider, embedding_model, _ = embedding_status()
    try:
        sandbox = await ExecutionProvider().readiness()
        sandbox_state = {"status": "ready", "languages": sorted(sandbox.get("languages", []))}
    except Exception:
        sandbox_state = {"status": "unavailable", "languages": []}
    heartbeat = await db.get(WorkerHeartbeat, "intervai-worker")
    now = datetime.now(timezone.utc)
    worker_recent = bool(heartbeat and (now - heartbeat.last_seen_at).total_seconds() < 30 and heartbeat.status == "running")
    counts = {}
    for state in ("queued", "running", "succeeded", "failed"):
        counts[state] = int(await db.scalar(select(func.count()).select_from(InterviewJob).where(InterviewJob.status == state)) or 0)
    submissions = {state: int(await db.scalar(select(func.count()).select_from(CodingSubmission).where(CodingSubmission.execution_status == state)) or 0) for state in ("QUEUED", "RUNNING", "COMPLETED", "SYSTEM_ERROR")}
    def safe_speech(kind):
        value = speech_status(kind)
        return {"provider": value.get("provider"), "configured": bool(value.get("configured"))}
    return {
        "checked_at": now.isoformat(), "database": database,
        "worker": {"status": "running" if worker_recent else "stale_or_unavailable", "last_seen_at": heartbeat.last_seen_at.isoformat() if heartbeat else None, "jobs": counts},
        "llm": {"status": "configured" if ready else "not_configured", "provider": llm_provider, "model": llm_model},
        "embedding": {"status": "configured" if embedding_ready else "not_configured", "provider": embedding_provider, "model": embedding_model},
        "speech": {"stt": safe_speech("stt"), "tts": safe_speech("tts")},
        "vision": vision_status(), "sandbox": sandbox_state, "coding_jobs": submissions,
    }


@router.get("/users")
async def users(actor: AdminActor, db: DB, role: str | None = Query(default=None, pattern="^(candidate|recruiter|admin)$"), query: str = Query(default="", max_length=120), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000)):
    statement = select(User).order_by(User.created_at.desc())
    if role:
        statement = statement.where(User.role == role)
    if query:
        statement = statement.where(User.email.ilike(f"%{query}%"))
    rows = (await db.scalars(statement.offset(offset).limit(limit))).all()
    return {"items": [{"id": str(row.id), "email": row.email, "display_name": row.display_name, "role": row.role, "disabled": row.disabled_at is not None, "created_at": row.created_at.isoformat()} for row in rows], "limit": limit, "offset": offset}


@router.get("/audit")
async def audit(actor: AdminActor, db: DB, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000)):
    rows = (await db.scalars(select(AdminAudit).order_by(AdminAudit.created_at.desc()).offset(offset).limit(limit))).all()
    return {"items": [{"id": str(row.id), "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None, "action": row.action, "resource_id": str(row.resource_id) if row.resource_id else None, "details": row.details, "created_at": row.created_at.isoformat()} for row in rows], "limit": limit, "offset": offset}


@router.patch("/users/{user_id}/role")
async def set_role(user_id: UUID, payload: AdminRoleInput, actor: AdminActor, db: DB, csrf: MutationActor):
    target = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        fail(404, "user_missing", "The account was not found.")
    if target.id == actor.user.id and payload.role != "admin":
        fail(409, "cannot_demote_self", "Another administrator must change your role.")
    if target.role == "admin" and payload.role != "admin":
        remaining = await db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.disabled_at.is_(None), User.id != target.id))
        if not remaining:
            fail(409, "last_admin", "At least one active administrator is required.")
    previous = target.role
    target.role = payload.role
    db.add(AdminAudit(actor_user_id=actor.user.id, action="user_role_changed", resource_id=target.id, details={"from": previous, "to": payload.role}))
    await db.commit()
    return {"id": str(target.id), "role": target.role}
