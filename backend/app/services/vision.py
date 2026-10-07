"""Durable aggregation, separate from the interview evaluation/memory pipelines."""

import asyncio
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import fail
from app.models.vision import IntegrityEvent, VisionSession
from app.providers.vision import VisionBusy, VisionError, get_vision, validate_frame, vision_status
from app.services import interviews

# Admission before executor submission: no cross-interview inference queue.
INFERENCE_SLOT = threading.Lock()


def now():
    return datetime.now(timezone.utc)


async def owned(db, actor, identifier, lock=True):
    candidate = await interviews.candidate(db, actor.user.id)
    interview = await interviews.owned(db, identifier, candidate.id, lock=lock)
    if lock:
        await db.refresh(interview)
    session = await db.scalar(
        select(VisionSession)
        .where(VisionSession.interview_id == interview.id)
        .execution_options(populate_existing=True)
    )
    if session is None and lock:
        session = VisionSession(
            interview_id=interview.id, enabled=False, revision=0, sequence=-1, aggregate={}
        )
        db.add(session)
        await db.flush()
    return interview, session


async def timeline(db, identifier):
    rows = (
        await db.scalars(
            select(IntegrityEvent)
            .where(IntegrityEvent.interview_id == identifier)
            .order_by(IntegrityEvent.started_at, IntegrityEvent.id)
            .limit(300)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "event_type": row.event_type,
            "severity": row.severity,
            "started_at": row.started_at.isoformat(),
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "duration_ms": row.duration_ms,
            "confidence": row.confidence,
            "detector": row.detector,
            "metadata": row.details,
        }
        for row in rows
    ]


async def output(db, interview, session):
    settings = get_settings()
    available = vision_status()
    if not interview.configuration.get("vision_enabled", True):
        available = {
            "available": False,
            "message": "Visual monitoring is disabled for this interview.",
        }
    return {
        "enabled": bool(session and session.enabled),
        "revision": session.revision if session else 0,
        "sequence": session.sequence if session else -1,
        "error_code": session.error_code if session else None,
        "last_observed_at": session.last_observed_at.isoformat()
        if session and session.last_observed_at
        else None,
        "policy": "camera_optional",
        "provider": available,
        "sampling": {
            "interval_ms": settings.vision_sample_interval_ms,
            "max_bytes": 131072,
            "max_dimension": 640,
            "absence_ms": settings.vision_absence_ms,
            "confirmation_ms": settings.vision_confirmation_ms,
        },
        "events": await timeline(db, interview.id),
    }


async def close_event(db, identifier, when):
    event = await db.get(IntegrityEvent, UUID(identifier))
    if event and event.ended_at is None:
        event.ended_at = max(event.started_at, when)
        event.duration_ms = round((event.ended_at - event.started_at).total_seconds() * 1000)


async def close_all(db, session):
    for channel in session.aggregate.values():
        if channel.get("event_id"):
            await close_event(db, channel["event_id"], session.last_observed_at or now())
    session.aggregate = {}


async def new_event(db, interview, session, kind, started, confidence, detector, details):
    count = await db.scalar(
        select(func.count())
        .select_from(IntegrityEvent)
        .where(IntegrityEvent.interview_id == interview.id)
    )
    if count >= 300:
        await close_all(db, session)
        session.enabled = False
        session.error_code = "event_limit"
        return None
    event = IntegrityEvent(
        candidate_id=interview.candidate_id,
        interview_id=interview.id,
        session_id=session.id,
        event_type=kind,
        severity="INFO"
        if kind in {"CANDIDATE_PRESENT", "CAMERA_ORIENTATION_CHANGED"}
        else "NOTICE"
        if kind in {"CANDIDATE_ABSENT", "CAMERA_INTERRUPTED"}
        else "REVIEW",
        started_at=started,
        confidence=confidence,
        detector=detector,
        details=details,
    )
    db.add(event)
    await db.flush()
    return event


async def aggregate(db, interview, session, detection, observed):
    """Confirm continuous sampled observations; gaps break continuity, not imply absence."""
    settings = get_settings()
    if session.last_observed_at and (observed - session.last_observed_at).total_seconds() > 4:
        await close_all(db, session)
        gap = await new_event(
            db,
            interview,
            session,
            "CAMERA_INTERRUPTED",
            session.last_observed_at,
            None,
            "server-sampling-gap",
            {"provenance": "server_observed_sampling_gap", "not_camera_proof": True},
        )
        if gap:
            await close_event(db, str(gap.id), observed)
    states = deepcopy(session.aggregate)
    desired = {
        "presence": (
            "CANDIDATE_PRESENT" if detection.persons else "CANDIDATE_ABSENT",
            detection.person_confidence if detection.persons else None,
        ),
        "multiple": (
            "MULTIPLE_PERSONS_DETECTED" if detection.persons > 1 else None,
            None,  # A box score is not confidence in an aggregate person count.
        ),
        "phone": (
            "PHONE_DETECTED"
            if detection.phone and interview.configuration.get("vision_phone_enabled", True)
            else None,
            detection.phone_confidence,
        ),
    }
    for key, (kind, confidence) in desired.items():
        state = states.get(key, {})
        if state.get("kind") != kind:
            if state.get("event_id"):
                await close_event(db, state["event_id"], session.last_observed_at or observed)
            state = {"kind": kind, "since": observed.isoformat()}
        if kind and not state.get("event_id"):
            threshold = (
                settings.vision_absence_ms
                if kind == "CANDIDATE_ABSENT"
                else settings.vision_confirmation_ms
            )
            if (
                observed - datetime.fromisoformat(state["since"])
            ).total_seconds() * 1000 >= threshold:
                event = await new_event(
                    db,
                    interview,
                    session,
                    kind,
                    datetime.fromisoformat(state["since"]),
                    confidence,
                    detection.detector,
                    {
                        "provenance": "server_inference",
                        "confidence_is_model_score": confidence is not None,
                    },
                )
                if event:
                    state["event_id"] = str(event.id)
        if state.get("event_id"):
            event = await db.get(IntegrityEvent, UUID(state["event_id"]))
            event.duration_ms = round((observed - event.started_at).total_seconds() * 1000)
        states[key] = state
    session.aggregate = states if session.enabled else {}
    session.last_observed_at = observed


async def frame(db, actor, identifier, revision, sequence, captured, data, content_type):
    observed = now()
    if captured.tzinfo is None or abs((observed - captured).total_seconds()) > 5:
        fail(409, "stale_frame", "Drop old frames and send the latest camera sample.")
    try:
        validate_frame(data, content_type)
    except VisionError as exc:
        fail(422, "invalid_frame", str(exc))
    interview, session = await owned(db, actor, identifier)
    if (
        not get_settings().vision_enabled
        or not interview.configuration.get("vision_enabled", True)
        or not session.enabled
    ):
        fail(409, "vision_disabled", "Visual monitoring is disabled.")
    if session.revision != revision or interview.status not in {
        "waiting_for_answer",
        "evaluating",
        "planning",
    }:
        fail(409, "stale_session", "Visual monitoring session is no longer active.")
    if sequence <= session.sequence:
        await db.commit()
        return await output(db, interview, session)
    if session.processing_until and session.processing_until > observed:
        fail(429, "vision_busy", "Drop this frame; a recent frame is still processing.")
    if (
        session.last_received_at
        and (observed - session.last_received_at).total_seconds() * 1000
        < get_settings().vision_sample_interval_ms * 0.8
    ):
        fail(429, "vision_rate_limit", "Drop this frame; sampling is too frequent.")
    session.sequence = sequence
    session.processing_sequence = sequence
    session.processing_until = observed + timedelta(seconds=10)
    session.last_received_at = observed
    await db.commit()  # no interview/database lock during inference
    try:
        if not INFERENCE_SLOT.acquire(blocking=False):
            raise VisionBusy("Drop this sample; local inference is busy.")

        def infer(payload=data):
            try:
                return get_vision().detect(payload)
            finally:
                INFERENCE_SLOT.release()

        detection = await asyncio.shield(asyncio.to_thread(infer))
        error = None
    except VisionBusy:
        detection, error = None, "vision_busy"
    except VisionError:
        detection, error = None, "vision_unavailable"
    finally:
        data = b""  # no filesystem storage or persisted frame payload
    await db.refresh(interview)
    await db.refresh(session)
    interview, session = await owned(db, actor, identifier)
    if (
        session.revision != revision
        or not session.enabled
        or session.processing_sequence != sequence
        or interview.status not in {"waiting_for_answer", "evaluating", "planning"}
    ):
        await db.commit()
        return await output(db, interview, session)
    session.processing_sequence = None
    session.processing_until = None
    session.error_code = error
    if detection:
        await aggregate(db, interview, session, detection, observed)
    else:
        await close_all(db, session)  # Unknown observations cannot confirm continuity.
    await db.commit()
    return await output(db, interview, session)


async def sweep_sessions(factory):
    """Existing worker maintenance closes abandoned sessions; never queues/persists frames."""
    from app.models.interviews import Interview

    async with factory() as db:
        ids = (
            await db.scalars(
                select(VisionSession.interview_id).where(VisionSession.enabled).limit(100)
            )
        ).all()
        for identifier in ids:
            interview = await db.scalar(
                select(Interview)
                .where(Interview.id == identifier)
                .with_for_update(skip_locked=True)
            )
            if interview is None:
                continue
            session = await db.scalar(
                select(VisionSession).where(VisionSession.interview_id == identifier)
            )
            reference = session.last_received_at or session.updated_at
            stale = (now() - reference).total_seconds() > 10
            inactive = interview.status not in {"waiting_for_answer", "planning", "evaluating"}
            if stale or inactive:
                await close_all(db, session)
                if stale and not inactive:
                    event = await new_event(
                        db,
                        interview,
                        session,
                        "CAMERA_INTERRUPTED",
                        reference,
                        None,
                        "server-sampling-gap",
                        {"provenance": "server_observed_sampling_gap", "not_camera_proof": True},
                    )
                    if event:
                        # No duration claim for the unobserved period after the last sample.
                        await close_event(db, str(event.id), event.started_at)
                session.enabled = False
                session.revision += 1
                session.processing_sequence = None
                session.processing_until = None
                session.error_code = "sampling_stopped" if stale else None
        await db.commit()
