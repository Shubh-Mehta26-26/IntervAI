from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.core.config import get_settings
from app.core.errors import fail
from app.providers.vision import vision_status
from app.schemas.vision import CameraNotice, VisionInput
from app.services import vision as service

router = APIRouter(prefix="/interviews/{identifier}", tags=["vision"])


@router.get("/vision/status")
async def status(identifier: UUID, actor: CandidateActor, db: DB):
    interview, session = await service.owned(db, actor, identifier, lock=False)
    return await service.output(db, interview, session)


@router.get("/integrity-events")
async def events(identifier: UUID, actor: CandidateActor, db: DB):
    interview, _ = await service.owned(db, actor, identifier, lock=False)
    return {
        "events": await service.timeline(db, interview.id),
        "note": "Observable signals only. Not proof of misconduct or skill evidence.",
    }


@router.post("/vision/session", dependencies=[Depends(csrf_actor)])
async def session(identifier: UUID, payload: VisionInput, actor: CandidateActor, db: DB):
    interview, row = await service.owned(db, actor, identifier)
    if row.revision != payload.expected_revision:
        fail(409, "stale_session", "Refresh visual monitoring status.")
    if payload.enabled:
        if not get_settings().vision_enabled:
            fail(409, "vision_disabled", "Visual monitoring is disabled by configuration.")
        if not interview.configuration.get("vision_enabled", True):
            fail(409, "vision_disabled", "Visual monitoring is disabled for this interview.")
        if not vision_status()["available"]:
            fail(
                409,
                "vision_unavailable",
                "Local visual monitoring is unavailable; continue without camera.",
            )
        if interview.status not in {"waiting_for_answer", "evaluating", "planning"}:
            fail(409, "invalid_state", "Start an active interview before enabling the camera.")
    await service.close_all(db, row)
    row.enabled = payload.enabled
    row.revision += 1
    row.sequence = -1
    row.processing_sequence = None
    row.processing_until = None
    row.last_received_at = None
    row.last_observed_at = None
    row.error_code = None
    await db.commit()
    return await service.output(db, interview, row)


@router.post("/vision/frame", dependencies=[Depends(csrf_actor)])
async def frame(
    identifier: UUID,
    actor: CandidateActor,
    db: DB,
    revision: int = Form(ge=0),
    sequence: int = Form(ge=0, le=100000),
    captured_at: datetime = Form(),
    image: UploadFile = File(),
):
    try:
        data = await image.read(131073)
        return await service.frame(
            db, actor, identifier, revision, sequence, captured_at, data, image.content_type
        )
    finally:
        await image.close()


@router.post("/vision/notice", dependencies=[Depends(csrf_actor)])
async def notice(identifier: UUID, payload: CameraNotice, actor: CandidateActor, db: DB):
    interview, row = await service.owned(db, actor, identifier)
    if not row.enabled or row.revision != payload.revision:
        fail(409, "stale_session", "Visual monitoring is not active.")
    if interview.status not in {"waiting_for_answer", "evaluating", "planning"}:
        fail(409, "invalid_state", "The interview is not active.")
    kind = "CAMERA_INTERRUPTED" if payload.notice == "interrupted" else "CAMERA_ORIENTATION_CHANGED"
    previous = (await service.timeline(db, interview.id))[-1:]
    if (
        not previous
        or previous[0]["event_type"] != kind
        or (service.now() - datetime.fromisoformat(previous[0]["started_at"])).total_seconds() >= 5
    ):
        if payload.notice == "interrupted":
            await service.close_all(db, row)
        event = await service.new_event(
            db,
            interview,
            row,
            kind,
            service.now(),
            None,
            "browser-camera-notice",
            {"provenance": "client_reported_unverified"},
        )
        if event:
            await service.close_event(db, str(event.id), event.started_at)
    await db.commit()
    return await service.output(db, interview, row)
