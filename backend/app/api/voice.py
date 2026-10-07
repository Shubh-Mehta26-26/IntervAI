from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from app.api.dependencies import DB, CandidateActor, csrf_actor
from app.core.config import get_settings
from app.core.errors import fail
from app.models.voice import VoiceTurn
from app.providers.speech import SpeechError, speech_status, wav_info
from app.schemas.identity import Input
from app.services import interviews
from app.services import voice as service

router = APIRouter(prefix="/interviews/{identifier}/voice", tags=["voice"])


class VoiceInput(Input):
    expected_revision: int = Field(ge=0)
    voice_revision: int = Field(ge=0)
    question_id: UUID
    idempotency_key: UUID


class EventInput(Input):
    expected_revision: int = Field(ge=0)
    voice_revision: int = Field(ge=0)
    event: str = Field(pattern="^(speaking|ready|listen|abort)$")


async def owned(db, actor, identifier):
    candidate = await interviews.candidate(db, actor.user.id)
    interview = await interviews.owned(db, identifier, candidate.id, lock=True)
    return interview, await service.session_for(db, interview)


def turn_out(turn):
    return {
        "id": str(turn.id),
        "question_id": str(turn.question_id),
        "kind": turn.kind,
        "status": turn.status,
        "operation_id": str(turn.operation_id),
        "answer_id": str(turn.answer_id) if turn.answer_id else None,
        "transcript": turn.transcript,
        "metrics": turn.metrics,
        "provider_metadata": turn.provider_metadata,
        "audio_metadata": turn.audio_metadata,
        "error_code": turn.error_code,
        "audio_available": bool(
            turn.kind == "tts"
            and turn.audio_key
            and turn.audio_expires_at
            and turn.audio_expires_at > datetime.now(timezone.utc)
        ),
    }


async def output(db, interview, session):
    turns = (
        await db.scalars(
            select(VoiceTurn)
            .where(VoiceTurn.session_id == session.id)
            .order_by(VoiceTurn.created_at.desc())
            .limit(20)
        )
    ).all()
    s = get_settings()
    return {
        "id": str(session.id),
        "state": session.state,
        "revision": session.revision,
        "interview_revision": interview.revision,
        "question_id": str(session.question_id) if session.question_id else None,
        "error_code": session.error_code,
        "stt": speech_status("stt"),
        "tts": speech_status("tts"),
        "capture": {
            "min_speech_seconds": s.voice_min_speech_seconds,
            "silence_seconds": s.voice_silence_seconds,
            "max_seconds": s.voice_max_seconds,
        },
        "turns": [turn_out(turn) for turn in turns],
    }


@router.post("/session", dependencies=[Depends(csrf_actor)])
async def create(identifier: UUID, actor: CandidateActor, db: DB):
    interview, session = await owned(db, actor, identifier)
    if interview.status not in {"waiting_for_answer", "evaluating", "planning", "paused"}:
        fail(409, "invalid_state", "Start an active interview before enabling voice.")
    await db.commit()
    return await output(db, interview, session)


@router.get("/status")
async def status(identifier: UUID, actor: CandidateActor, db: DB):
    interview, session = await owned(db, actor, identifier)
    await db.commit()
    return await output(db, interview, session)


@router.post("/event", dependencies=[Depends(csrf_actor)])
async def event(identifier: UUID, payload: EventInput, actor: CandidateActor, db: DB):
    interview, session = await owned(db, actor, identifier)
    interviews.check_revision(interview, payload.expected_revision)
    service.check(session, payload.voice_revision)
    if interview.status != "waiting_for_answer":
        fail(409, "invalid_state", "The interview is not waiting for an answer.")
    transitions = {
        "speaking": ({"playing_response", "ready_for_candidate"}, "ai_speaking"),
        "ready": ({"ai_speaking", "playing_response"}, "ready_for_candidate"),
        "listen": ({"ready_for_candidate", "error"}, "listening"),
        "abort": (
            {"listening", "ready_for_candidate", "ai_speaking", "playing_response", "error"},
            "ready_for_candidate",
        ),
    }
    allowed, state = transitions[payload.event]
    if payload.event == "speaking":
        audio = await db.scalar(
            select(VoiceTurn).where(
                VoiceTurn.session_id == session.id,
                VoiceTurn.question_id == session.question_id,
                VoiceTurn.kind == "tts",
                VoiceTurn.status == "ready",
                VoiceTurn.audio_key.is_not(None),
                VoiceTurn.audio_expires_at > datetime.now(timezone.utc),
            )
        )
        if not audio:
            fail(409, "audio_missing", "Generate question audio before playback.")
    if session.state not in allowed:
        fail(409, "invalid_voice_state", "Voice is not ready for that action.")
    session.state, session.error_code = state, None
    session.revision += 1
    await db.commit()
    return await output(db, interview, session)


@router.post("/synthesize", status_code=202, dependencies=[Depends(csrf_actor)])
async def synthesize(identifier: UUID, payload: VoiceInput, actor: CandidateActor, db: DB):
    interview, session = await owned(db, actor, identifier)
    digest = service.fingerprint("tts", payload.question_id)
    duplicate = await db.scalar(
        select(VoiceTurn).where(VoiceTurn.request_key == payload.idempotency_key)
    )
    if duplicate:
        if duplicate.session_id != session.id or duplicate.payload_hash != digest:
            fail(409, "idempotency_conflict", "This speech request key is already in use.")
        return turn_out(duplicate)
    interviews.check_revision(interview, payload.expected_revision)
    service.check(session, payload.voice_revision)
    if (
        interview.status != "waiting_for_answer"
        or session.question_id != payload.question_id
        or session.state not in {"ready_for_candidate", "error", "playing_response"}
    ):
        fail(409, "invalid_voice_state", "Reload the current question before playback.")
    return turn_out(
        await service.queue(db, interview, session, "tts", payload.idempotency_key, digest)
    )


@router.post("/transcribe", status_code=202, dependencies=[Depends(csrf_actor)])
async def transcribe(
    identifier: UUID,
    actor: CandidateActor,
    db: DB,
    file: UploadFile = File(),
    question_id: UUID = Form(),
    expected_revision: int = Form(ge=0),
    voice_revision: int = Form(ge=0),
    idempotency_key: UUID = Form(),
):
    interview, session = await owned(db, actor, identifier)
    try:
        if file.content_type not in {"audio/wav", "audio/x-wav", "audio/wave"}:
            fail(415, "invalid_audio_type", "Upload a mono PCM WAV recording.")
        audio = await file.read(service.MAX_AUDIO_BYTES + 1)
        if len(audio) > service.MAX_AUDIO_BYTES:
            fail(413, "audio_too_large", "Audio exceeds the 6 MB limit.")
        try:
            wav_info(audio, get_settings().voice_max_seconds)
        except SpeechError as exc:
            fail(422, "invalid_audio", str(exc))
    finally:
        await file.close()
    digest = service.fingerprint("stt", question_id, audio)
    duplicate = await db.scalar(select(VoiceTurn).where(VoiceTurn.request_key == idempotency_key))
    if duplicate:
        if duplicate.session_id != session.id or duplicate.payload_hash != digest:
            fail(409, "idempotency_conflict", "This speech request key is already in use.")
        return turn_out(duplicate)
    interviews.check_revision(interview, expected_revision)
    service.check(session, voice_revision)
    if (
        interview.status != "waiting_for_answer"
        or session.question_id != question_id
        or session.state != "listening"
    ):
        fail(409, "invalid_voice_state", "Start listening to answer the current question.")
    return turn_out(
        await service.queue(db, interview, session, "stt", idempotency_key, digest, audio)
    )


@router.get("/audio/{turn_id}")
async def audio(identifier: UUID, turn_id: UUID, actor: CandidateActor, db: DB):
    interview, session = await owned(db, actor, identifier)
    turn = await db.get(VoiceTurn, turn_id)
    if not turn or turn.session_id != session.id:
        fail(404, "audio_missing", "Audio was not found.")
    if interview.status != "waiting_for_answer" or turn.question_id != session.question_id:
        fail(409, "invalid_state", "Audio is only available for the active question.")
    if (
        turn.kind != "tts"
        or turn.status != "ready"
        or not turn.audio_key
        or turn.audio_expires_at <= datetime.now(timezone.utc)
    ):
        fail(410, "audio_expired", "Playback expired. Generate the question audio again.")
    try:
        data = service.AudioStorage().path(turn.audio_key).read_bytes()
    except FileNotFoundError:
        fail(410, "audio_expired", "Playback expired. Generate the question audio again.")
    await db.commit()
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})
