import array
import asyncio
import hashlib
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import fail
from app.models.interviews import Interview, InterviewJob, InterviewQuestion
from app.models.voice import VoiceSession, VoiceTurn
from app.providers.speech import SpeechError, Transcript, get_stt, get_tts, wav_info

MAX_AUDIO_BYTES = 6 * 1024 * 1024


class AudioStorage:
    def __init__(self):
        self.root = (get_settings().storage_root / "voice").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        if not re.fullmatch(r"[0-9a-f]{32}\.wav", key):
            raise SpeechError("Invalid audio reference.")
        path = self.root / key
        if path.is_symlink():
            raise SpeechError("Invalid audio reference.")
        return path

    def save(self, data):
        key = uuid4().hex + ".wav"
        with self.path(key).open("xb") as target:
            target.write(data)
        return key

    def delete(self, key):
        if key:
            self.path(key).unlink(missing_ok=True)

    def sweep(self):
        deadline = datetime.now(timezone.utc).timestamp() - get_settings().voice_audio_ttl_seconds
        for path in self.root.glob("*.wav"):
            if re.fullmatch(r"[0-9a-f]{32}\.wav", path.name) and not path.is_symlink():
                try:
                    if path.stat().st_mtime < deadline:
                        path.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass


def measurements(data, metadata, text):
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    rate, step = metadata["sample_rate"], metadata["sample_rate"] // 50
    windows = [samples[i : i + step] for i in range(0, len(samples), step)]
    active = [math.sqrt(sum(x * x for x in part) / len(part)) / 32768 >= 0.012 for part in windows]
    speech = sum(len(part) / rate for part, yes in zip(windows, active, strict=True) if yes)
    pauses, silent = 0, 0
    first, last = (
        next((i for i, v in enumerate(active) if v), len(active)),
        next((i for i in range(len(active) - 1, -1, -1) if active[i]), -1),
    )
    for value in active[first : last + 1]:
        if value:
            pauses += int(silent >= 15)
            silent = 0
        else:
            silent += 1
    words = re.findall(r"\b[\w']+\b", text)
    filler_counts = {
        f: len(re.findall(r"(?<!\w)" + re.escape(f) + r"(?!\w)", text, re.I))
        for f in get_settings().speech_fillers
        if f.strip()
    }
    duration = metadata["duration_seconds"]
    return {
        "duration_seconds": round(duration, 3),
        "speech_duration_seconds": round(speech, 3),
        "silence_duration_seconds": round(duration - speech, 3),
        "pause_count": pauses,
        "speaking_rate_wpm": round(len(words) * 60 / speech, 2) if speech else None,
        "word_count": len(words),
        "transcript_length": len(text),
        "filler_counts": filler_counts,
        "filler_count": sum(filler_counts.values()),
        "method": "pcm_rms_20ms_threshold_0.012",
        "note": "Signal activity estimate; background noise can count as speech. No scoring effect.",
    }


async def synchronize(db, interview, session):
    question = await db.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_id == interview.id,
            InterviewQuestion.sequence == interview.current_question,
        )
    )
    question_id = question.id if question else None
    desired = None
    if interview.status in {"planning", "evaluating"}:
        desired = "generating_response" if interview.status == "planning" else "evaluating"
    elif interview.status != "waiting_for_answer":
        desired = "idle"
    elif session.question_id != question_id or session.state in {"idle", "evaluating"}:
        desired = "ready_for_candidate"
    if session.question_id != question_id or (desired and desired != session.state):
        session.question_id = question_id
        session.state = desired or "ready_for_candidate"
        session.revision += 1
        session.error_code = None
        await db.flush()
    return session


async def session_for(db, interview):
    session = await db.scalar(
        select(VoiceSession).where(VoiceSession.interview_id == interview.id).with_for_update()
    )
    if not session:
        session = VoiceSession(interview_id=interview.id)
        db.add(session)
        await db.flush()
    return await synchronize(db, interview, session)


def check(session, expected):
    if session.revision != expected:
        fail(409, "stale_voice_request", "Voice state changed. Reload before continuing.")


async def queue(db, interview, session, kind, request_key, fingerprint, audio=None):
    duplicate = await db.scalar(select(VoiceTurn).where(VoiceTurn.request_key == request_key))
    if duplicate:
        if duplicate.session_id != session.id or duplicate.payload_hash != fingerprint:
            fail(409, "idempotency_conflict", "This speech request key is already in use.")
        return duplicate
    active = await db.scalar(
        select(VoiceTurn).where(
            VoiceTurn.session_id == session.id, VoiceTurn.status.in_(["queued", "processing"])
        )
    )
    if active:
        fail(409, "voice_busy", "A speech operation is already processing.")
    job = InterviewJob(
        interview_id=interview.id,
        kind=kind,
        expected_revision=interview.revision,
        dedupe_key=f"voice:{request_key}",
        max_attempts=1,
    )
    db.add(job)
    await db.flush()
    turn = VoiceTurn(
        session_id=session.id,
        question_id=session.question_id,
        operation_id=job.id,
        kind=kind,
        request_key=request_key,
        payload_hash=fingerprint,
    )
    if audio:
        metadata, _ = wav_info(audio, get_settings().voice_max_seconds)
        turn.audio_metadata = metadata
        turn.audio_key = AudioStorage().save(audio)
        turn.audio_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=get_settings().voice_audio_ttl_seconds
        )
    db.add(turn)
    session.state = "processing_audio" if kind == "stt" else "generating_response"
    session.revision += 1
    session.error_code = None
    try:
        await db.commit()
    except Exception:
        if audio:
            AudioStorage().delete(turn.audio_key)
        raise
    await db.refresh(turn)
    return turn


async def process_speech_job(factory, identifier, claim, stt=None, tts=None):
    storage = AudioStorage()
    key, result_key = None, None
    try:
        async with factory() as db:
            job = await db.get(InterviewJob, identifier)
            turn = await db.scalar(select(VoiceTurn).where(VoiceTurn.operation_id == identifier))
            session = await db.get(VoiceSession, turn.session_id)
            interview = await db.get(Interview, job.interview_id)
            if job.claim_id != claim or job.status != "running":
                return
            key = turn.audio_key
            if job.attempts > 3:
                raise SpeechError("Speech processing was interrupted repeatedly.")
            if (
                interview.status != "waiting_for_answer"
                or interview.revision != job.expected_revision
                or session.question_id != turn.question_id
            ):
                turn.status, job.status = "cancelled", "cancelled"
                turn.audio_key = None
                await db.commit()
                return
            turn.status = "processing"
            session.state = "transcribing" if turn.kind == "stt" else "generating_response"
            session.revision += 1
            question = await db.get(InterviewQuestion, turn.question_id)
            text, kind = question.text, turn.kind
            await db.commit()
        async with asyncio.timeout(get_settings().speech_timeout_seconds + 2):
            if kind == "stt":
                audio = storage.path(key).read_bytes()
                metadata, pcm = wav_info(audio, get_settings().voice_max_seconds)
                provider = stt or get_stt()
                transcript = Transcript.model_validate(
                    (await provider.transcribe(audio)).model_dump()
                )
                if not transcript.text.strip():
                    raise SpeechError(
                        "No speech was transcribed. Retry or type your answer instead."
                    )
                if any(
                    segment.end > metadata["duration_seconds"] + 0.1
                    for segment in transcript.segments
                ):
                    raise SpeechError("Speech provider returned invalid segment timing.")
                metrics = measurements(pcm, metadata, transcript.text)
            else:
                provider = tts or get_tts()
                audio = await provider.synthesize(text)
                metadata, _ = wav_info(audio, 180, input_audio=False)
                result_key = storage.save(audio)
        async with factory() as db:
            # Lock in the same order as requests: interview, session, then turn/job.
            job = await db.get(InterviewJob, identifier)
            interview = await db.scalar(
                select(Interview).where(Interview.id == job.interview_id).with_for_update()
            )
            turn = await db.scalar(
                select(VoiceTurn).where(VoiceTurn.operation_id == identifier).with_for_update()
            )
            session = await db.get(VoiceSession, turn.session_id)
            if (
                job.claim_id != claim
                or job.status != "running"
                or interview.revision != job.expected_revision
                or interview.status != "waiting_for_answer"
                or session.question_id != turn.question_id
            ):
                if job.claim_id == claim:
                    job.status, turn.status = "cancelled", "cancelled"
                    turn.audio_key = None
                    await db.commit()
                return
            turn.audio_key = result_key
            turn.audio_metadata = metadata
            turn.provider_metadata = {"provider": provider.name, "model": provider.model}
            if kind == "stt":
                turn.transcript = transcript.text
                turn.provider_metadata = {
                    **turn.provider_metadata,
                    **transcript.model_dump(exclude={"text"}, exclude_none=True),
                }
                turn.metrics = metrics
                session.state = "ready_for_candidate"
            else:
                turn.audio_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=get_settings().voice_audio_ttl_seconds
                )
                session.state = "playing_response"
            session.revision += 1
            turn.status, job.status, job.lease_until = "ready", "succeeded", None
            await db.commit()
            result_key = None  # Ownership transferred to the persisted TTS reference.
    except Exception as exc:
        code = exc.code if isinstance(exc, SpeechError) else "speech_failed"
        async with factory() as db:
            job = await db.get(InterviewJob, identifier)
            interview = await db.scalar(
                select(Interview).where(Interview.id == job.interview_id).with_for_update()
            )
            turn = await db.scalar(
                select(VoiceTurn).where(VoiceTurn.operation_id == identifier).with_for_update()
            )
            session = await db.get(VoiceSession, turn.session_id)
            if job.claim_id == claim and job.status == "running":
                job.status, job.error_code, job.lease_until = "failed", code, None
                job.error_message = "Voice unavailable. You can type your answer instead."
                turn.status, turn.error_code, turn.audio_key = "failed", code, None
                if (
                    interview.revision == job.expected_revision
                    and session.question_id == turn.question_id
                ):
                    session.state, session.error_code = "error", code
                    session.revision += 1
                await db.commit()
    finally:
        storage.delete(key)
        storage.delete(result_key)


async def link_answer(db, interview, payload, answer):
    if payload.voice_turn_id is None:
        return
    session = await db.scalar(
        select(VoiceSession).where(VoiceSession.interview_id == interview.id).with_for_update()
    )
    turn = await db.get(VoiceTurn, payload.voice_turn_id)
    if not session or not turn or turn.session_id != session.id:
        fail(404, "voice_turn_missing", "Voice transcript was not found.")
    if (
        turn.kind != "stt"
        or turn.status != "ready"
        or turn.question_id != answer.question_id
        or not turn.transcript
    ):
        fail(409, "voice_turn_invalid", "Review a ready transcript for the current question.")
    turn.answer_id, turn.status = answer.id, "submitted"
    answer.duration_seconds = round(turn.audio_metadata["duration_seconds"])
    session.state, session.revision = "evaluating", session.revision + 1


def fingerprint(kind, question_id, data=b""):
    return hashlib.sha256(kind.encode() + str(question_id).encode() + data).hexdigest()
