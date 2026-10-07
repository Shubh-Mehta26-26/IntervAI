"""Test-only speech fixtures; no live credentials, microphone or transcript fabrication in prod."""

import io
import math
import struct
import wave
from uuid import uuid4

import httpx
import pytest
from app.core.config import get_settings
from app.providers.llm import GeminiProvider, LLMError, LLMOutputError, provider_status
from app.providers.speech import (
    OpenAISTT,
    OpenAITTS,
    SpeechError,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    get_stt,
    speech_status,
    wav_info,
)
from app.schemas.interviews import QuestionResult
from app.services.voice import AudioStorage, measurements
from app.worker import process_interview_one
from conftest import Harness, run
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_interviews import (
    FakeEmbeddingProvider,
    FakeProvider,
    create_interview,
    mutate,
    signed_in,
    worker,
)


def wav(seconds=1):
    target = io.BytesIO()
    with wave.open(target, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(i * 0.1)))
                for i in range(int(seconds * 16000))
            )
        )
    return target.getvalue()


class TestSTT(SpeechToTextProvider):
    __test__ = False
    name, model = "test-only", "fixture-stt"
    calls = 0

    async def transcribe(self, audio):
        self.calls += 1
        wav_info(audio)
        return Transcript(
            text="Um, I used typed validation and async handlers. You know, transactions keep writes consistent."
        )


class TestTTS(TextToSpeechProvider):
    __test__ = False
    name, model = "test-only", "fixture-tts"
    calls = 0

    async def synthesize(self, text):
        self.calls += 1
        assert len(text) > 10
        return wav()


class BrokenSTT(TestSTT):
    async def transcribe(self, audio):
        raise SpeechError("Test-only provider failure")


class BrokenTTS(TestTTS):
    async def synthesize(self, text):
        raise SpeechError("Test-only provider failure")


def voice_worker(identity, stt=None, tts=None):
    engine = create_async_engine(identity.url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def work():
        try:
            return await process_interview_one(
                factory, FakeProvider(), FakeEmbeddingProvider(), stt, tts
            )
        finally:
            await engine.dispose()

    return run(work())


def active(identity):
    signed_in(identity)
    row = create_interview(identity).json()
    mutate(
        identity, "POST", f"/interviews/{row['id']}/start", {"expected_revision": row["revision"]}
    )
    worker(identity, FakeProvider())
    return identity.request("GET", f"/interviews/{row['id']}").json()


def voice(identity, row):
    return identity.request("GET", f"/interviews/{row['id']}/voice/status").json()


def event(identity, row, action, current=None):
    current = current or voice(identity, row)
    return mutate(
        identity,
        "POST",
        f"/interviews/{row['id']}/voice/event",
        {
            "expected_revision": row["revision"],
            "voice_revision": current["revision"],
            "event": action,
        },
    )


def upload(identity, row, current, audio=None, key=None, content_type="audio/wav"):
    return identity.request(
        "POST",
        f"/interviews/{row['id']}/voice/transcribe",
        headers={"X-CSRF-Token": identity.csrf},
        data={
            "question_id": row["current"]["id"],
            "expected_revision": row["revision"],
            "voice_revision": current["revision"],
            "idempotency_key": str(key or uuid4()),
        },
        files={"file": ("untrusted-name.wav", wav() if audio is None else audio, content_type)},
    )


def speech_payload(row, current):
    return {
        "expected_revision": row["revision"],
        "voice_revision": current["revision"],
        "question_id": row["current"]["id"],
        "idempotency_key": str(uuid4()),
    }


def test_voice_flow_converges_and_original_transcript_is_immutable(identity, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    row = active(identity)
    current = voice(identity, row)
    assert current["state"] == "ready_for_candidate"
    assert (
        mutate(identity, "POST", f"/interviews/{row['id']}/voice/session", {}).json()["id"]
        == current["id"]
    )
    payload = speech_payload(row, current)
    turn = mutate(identity, "POST", f"/interviews/{row['id']}/voice/synthesize", payload).json()
    provider = TestTTS()
    voice_worker(identity, tts=provider)
    current = voice(identity, row)
    assert current["state"] == "playing_response"
    response = identity.request("GET", f"/interviews/{row['id']}/voice/audio/{turn['id']}")
    assert response.status_code == 200 and response.content[:4] == b"RIFF"
    assert event(identity, row, "speaking").json()["state"] == "ai_speaking"
    assert event(identity, row, "ready").json()["state"] == "ready_for_candidate"
    current = event(identity, row, "listen").json()
    key = uuid4()
    response = upload(identity, row, current, key=key)
    assert response.status_code == 202
    assert upload(identity, row, current, key=key).json()["id"] == response.json()["id"]
    assert upload(identity, row, current, audio=wav(2), key=key).status_code == 409
    stt = TestSTT()
    voice_worker(identity, stt=stt)
    assert len(list((tmp_path / "voice").glob("*.wav"))) == 1  # Only temporary TTS remains.
    current = voice(identity, row)
    transcribed = current["turns"][0]
    assert transcribed["status"] == "ready" and transcribed["transcript"].startswith("Um,")
    assert "confidence" not in transcribed["provider_metadata"]
    assert transcribed["metrics"]["filler_count"] == 2
    assert stt.calls == provider.calls == 1
    assert (
        identity.sql("SELECT audio_key FROM voice_turns WHERE kind='stt'")[0]["audio_key"] is None
    )
    answer = {
        "question_id": row["current"]["id"],
        "text": transcribed["transcript"] + " Reviewed detail.",
        "voice_turn_id": transcribed["id"],
        "duration_seconds": 1,
        "expected_revision": row["revision"],
        "idempotency_key": str(uuid4()),
    }
    response = mutate(identity, "POST", f"/interviews/{row['id']}/answers", answer)
    assert response.status_code == 202
    assert (
        mutate(identity, "POST", f"/interviews/{row['id']}/answers", answer).json()["operation_id"]
        == response.json()["operation_id"]
    )
    assert voice(identity, row)["state"] == "evaluating"
    llm = FakeProvider()
    worker(identity, llm)
    assert any(
        transcribed["transcript"] in body for name, body in llm.calls if "evaluation" in name
    )
    row = identity.request("GET", f"/interviews/{row['id']}").json()
    assert row["status"] == "waiting_for_answer" and row["current"]["sequence"] == 2
    assert voice(identity, row)["state"] == "ready_for_candidate"
    answers = identity.request("GET", f"/interviews/{row['id']}/answers").json()
    assert answers[0]["evaluation"] and answers[0]["decision"]
    saved = identity.sql("SELECT transcript,answer_id FROM voice_turns WHERE kind='stt'")[0]
    assert (
        saved["transcript"] == transcribed["transcript"]
        and str(saved["answer_id"]) == answers[0]["id"]
    )
    with pytest.raises(Exception):
        identity.sql("UPDATE voice_turns SET transcript='rewritten' WHERE kind='stt'")
    final = {
        "question_id": row["current"]["id"],
        "text": "I used typed validation and async handlers",
        "expected_revision": row["revision"],
        "idempotency_key": str(uuid4()),
    }
    assert mutate(identity, "POST", f"/interviews/{row['id']}/answers", final).status_code == 202
    worker(identity, FakeProvider())
    assert identity.request("GET", f"/interviews/{row['id']}").json()["status"] == "completed"


@pytest.mark.parametrize("kind", ["stt", "tts"])
def test_provider_failure_keeps_text_working(identity, tmp_path, monkeypatch, kind):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    row = active(identity)
    if kind == "stt":
        upload(identity, row, event(identity, row, "listen").json())
    else:
        mutate(
            identity,
            "POST",
            f"/interviews/{row['id']}/voice/synthesize",
            speech_payload(row, voice(identity, row)),
        )
    voice_worker(identity, BrokenSTT(), BrokenTTS())
    current = voice(identity, row)
    assert current["state"] == "error" and current["turns"][0]["transcript"] is None
    assert list((tmp_path / "voice").glob("*.wav")) == []
    assert (
        identity.request("GET", f"/interviews/{row['id']}").json()["status"] == "waiting_for_answer"
    )
    answer = {
        "question_id": row["current"]["id"],
        "text": "Typed fallback with validation and async handlers",
        "expected_revision": row["revision"],
        "idempotency_key": str(uuid4()),
    }
    assert mutate(identity, "POST", f"/interviews/{row['id']}/answers", answer).status_code == 202
    worker(identity, FakeProvider())
    assert identity.request("GET", f"/interviews/{row['id']}").json()["current"]["sequence"] == 2


@pytest.mark.parametrize(
    "audio,content_type,status",
    [
        (b"not audio", "audio/wav", 422),
        (b"not audio", "text/plain", 415),
        (b"x" * (6 * 1024 * 1024 + 1), "audio/wav", 413),
        (wav(0.05), "audio/wav", 422),
    ],
    ids=["bad-wav", "bad-content-type", "oversized", "too-short"],
)
def test_audio_validation(identity, audio, content_type, status):
    row = active(identity)
    response = upload(
        identity, row, event(identity, row, "listen").json(), audio=audio, content_type=content_type
    )
    assert response.status_code == status
    assert identity.sql("SELECT count(*) AS n FROM voice_turns")[0]["n"] == 0


def test_ownership_states_and_stale_requests(identity):
    row = active(identity)
    current = voice(identity, row)
    assert upload(identity, row, current).status_code == 409
    assert event(identity, row, "speaking", current).status_code == 409
    listening = event(identity, row, "listen", current).json()
    assert event(identity, row, "abort", current).status_code == 409
    assert event(identity, row, "abort", listening).status_code == 200
    other = Harness(identity.url)
    assert other.register("voice-other@example.com").status_code == 201
    assert other.login("voice-other@example.com").status_code == 200
    assert other.request("GET", f"/interviews/{row['id']}/voice/status").status_code == 404
    assert upload(other, row, current).status_code == 404
    unsigned = Harness(identity.url)
    assert unsigned.request("GET", f"/interviews/{row['id']}/voice/status").status_code == 401
    assert (
        identity.request("POST", f"/interviews/{row['id']}/voice/session", json={}).status_code
        == 403
    )
    mutate(
        identity, "POST", f"/interviews/{row['id']}/pause", {"expected_revision": row["revision"]}
    )
    assert event(identity, row, "listen").status_code == 409


def test_stale_job_discards_audio(identity, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    row = active(identity)
    upload(identity, row, event(identity, row, "listen").json())
    mutate(
        identity, "POST", f"/interviews/{row['id']}/pause", {"expected_revision": row["revision"]}
    )
    provider = TestSTT()
    voice_worker(identity, stt=provider)
    assert provider.calls == 0 and list((tmp_path / "voice").glob("*.wav")) == []
    assert identity.sql("SELECT status FROM voice_turns")[0]["status"] == "cancelled"


def test_missing_config_and_metrics(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "vosk_model_path", None)
    monkeypatch.setattr(settings, "stt_provider", "vosk")
    assert speech_status("stt")["configured"] is False
    with pytest.raises(SpeechError):
        get_stt()
    metadata, pcm = wav_info(wav())
    metrics = measurements(pcm, metadata, "um uh you know seven words")
    assert metrics["filler_count"] == 3 and metrics["word_count"] == 6
    assert metrics["speech_duration_seconds"] == 1
    assert metrics["speaking_rate_wpm"] == 360
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    storage = AudioStorage()
    with pytest.raises(SpeechError):
        storage.path("../../private.env")


@pytest.mark.parametrize(
    "failure", ["timeout", "rate_limit", "auth", "malformed", "refusal", "success"]
)
def test_gemini_provider_contract(monkeypatch, failure):
    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, json):
            assert "key=" not in url and "x-goog-api-key" in headers
            assert json["generationConfig"]["responseMimeType"] == "application/json"
            if failure == "timeout":
                raise httpx.ReadTimeout("test-only")
            content = {
                "question": "Explain an API validation trade-off.",
                "topic": "Python",
                "difficulty": 2,
                "question_type": "technical",
                "reason": "test-only",
            }
            body = {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": __import__("json").dumps(content)}]},
                    }
                ]
            }
            if failure == "malformed":
                body = {"candidates": "invalid"}
            if failure == "refusal":
                body["candidates"][0]["finishReason"] = "SAFETY"
            return httpx.Response(
                429 if failure == "rate_limit" else 401 if failure == "auth" else 200,
                json=body,
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    # An empty test-only auth value; no real or invented provider credential.
    provider = GeminiProvider("", "test-only-model", 10)
    if failure == "success":
        assert (
            run(
                provider.structured(
                    system="Test", user="Test", schema=QuestionResult, name="question"
                )
            ).topic
            == "Python"
        )
    else:
        with pytest.raises((LLMError, LLMOutputError)):
            run(
                provider.structured(
                    system="Test", user="Test", schema=QuestionResult, name="question"
                )
            )


def test_provider_configuration_is_independent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_model", "test-only-model")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert provider_status()[0] is False and "GEMINI_API_KEY" in provider_status()[3]
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_model", "test-only-alternative")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    assert provider_status()[2] == "test-only-alternative"


@pytest.mark.parametrize("failure", ["timeout", "rate-limit", "auth", "malformed", "success"])
def test_cloud_speech_contracts(monkeypatch, failure):
    original = httpx.AsyncClient

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test-only")
        code = 429 if failure == "rate-limit" else 401 if failure == "auth" else 200
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(
                code,
                json={"text": "Actual test fixture transcript"}
                if failure != "malformed"
                else {"text": None},
            )
        return httpx.Response(code, content=wav() if failure != "malformed" else b"bad audio")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    stt, tts = OpenAISTT("test-only-model", ""), OpenAITTS("test-only-model", "")
    if failure == "success":
        transcript = run(stt.transcribe(wav()))
        assert transcript.text == "Actual test fixture transcript" and transcript.confidence is None
        assert wav_info(run(tts.synthesize("Test-only playback")))[0]["duration_seconds"] == 1
    elif failure == "malformed":
        with pytest.raises(SpeechError):
            run(stt.transcribe(wav()))
        with pytest.raises(SpeechError):
            wav_info(run(tts.synthesize("Test-only playback")))
    else:
        with pytest.raises(SpeechError):
            run(stt.transcribe(wav()))
        with pytest.raises(SpeechError):
            run(tts.synthesize("Test-only playback"))


def test_signal_metrics_pauses_and_transcript_validation():
    metadata, pcm = wav_info(wav())
    silence = b"\x00" * 16000
    measured = measurements(pcm + silence + pcm, {**metadata, "duration_seconds": 2.5}, "one two")
    assert measured["pause_count"] == 1 and measured["silence_duration_seconds"] == 0.5
    with pytest.raises(ValueError):
        Transcript(text="test", confidence=float("nan"))
    with pytest.raises(ValueError):
        Transcript(text="test", segments=[{"start": 2, "end": 1}])


def test_temporary_audio_expiry(monkeypatch, tmp_path):
    import os
    import time

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    store = AudioStorage()
    key = store.save(wav())
    os.utime(store.path(key), (time.time() - 7200, time.time() - 7200))
    store.sweep()
    assert not store.path(key).exists()
