"""Speech HTTP contracts with synthetic audio; no network or credentials."""

import base64
import json

import httpx
import pytest
from app.core.config import get_settings
from app.providers.speech import GeminiSTT, GeminiTTS, SpeechError, speech_status
from conftest import run
from test_voice import wav


def transport(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


def payload(parts, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": parts}}]}


def test_neural_tts_keeps_question_separate_from_style(monkeypatch):
    question = "How would you use PostgreSQL?"

    def handler(request):
        assert "key=" not in str(request.url)
        data = json.loads(request.content)
        part = data["contents"][0]["parts"][0]
        assert part["text"] == question
        assert "pauses" in part["speech_metadata"]["style"]
        return httpx.Response(
            200,
            json=payload(
                [
                    {
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": base64.b64encode(wav()).decode(),
                        }
                    }
                ]
            ),
        )

    transport(monkeypatch, handler)
    assert run(GeminiTTS("test-only", "").synthesize(question)) == wav()


def test_transcription_uses_verbatim_audio_and_preserves_errors(monkeypatch):
    spoken = "Um, PostgreSQL is, is a programming language."

    def handler(request):
        data = json.loads(request.content)
        parts = data["contents"][0]["parts"]
        assert len(parts) == 1 and "text" not in parts[0]
        assert base64.b64decode(parts[0]["inlineData"]["data"]) == wav()
        config = data["generationConfig"]["audioTranscriptionConfig"]
        assert config["mode"] == "VERBATIM" and "PostgreSQL" in config["customVocabulary"]
        return httpx.Response(200, json=payload([{"audioTranscription": {"text": spoken}}]))

    transport(monkeypatch, handler)
    result = run(GeminiSTT("test-only", "").transcribe(wav()))
    assert result.text == spoken
    assert result.confidence is None and result.segments == []


@pytest.mark.parametrize(
    "failure", ["auth", "quota", "timeout", "json", "shape", "blocked", "empty", "text-only"]
)
def test_bad_transcription_never_becomes_a_candidate_answer(monkeypatch, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test-only")
        if failure in {"auth", "quota"}:
            return httpx.Response(401 if failure == "auth" else 429)
        if failure == "json":
            return httpx.Response(200, content=b"not json")
        if failure == "shape":
            return httpx.Response(200, json={"candidates": [None]})
        return httpx.Response(
            200,
            json=payload(
                [{"text": "A suggested answer"}]
                if failure == "text-only"
                else [{"audioTranscription": {"text": ""}}],
                "SAFETY" if failure == "blocked" else "STOP",
            ),
        )

    transport(monkeypatch, handler)
    with pytest.raises(SpeechError):
        run(GeminiSTT("test-only", "").transcribe(wav()))


@pytest.mark.parametrize(
    "content",
    [
        {"mimeType": "audio/wav", "data": "!invalid-base64!"},
        {"mimeType": "audio/wav", "data": base64.b64encode(b"invalid WAV").decode()},
        {"mimeType": "text/plain", "data": ""},
    ],
)
def test_bad_tts_audio_cannot_reach_playback(monkeypatch, content):
    transport(
        monkeypatch, lambda request: httpx.Response(200, json=payload([{"inlineData": content}]))
    )
    with pytest.raises(SpeechError):
        run(GeminiTTS("test-only", "").synthesize("Test question"))


def test_cloud_disclosure_and_missing_key(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stt_provider", "gemini")
    monkeypatch.setattr(s, "stt_model", "test-only")
    monkeypatch.setattr(s, "gemini_api_key", None)
    monkeypatch.setattr(s, "stt_api_key", None)
    assert speech_status("stt")["cloud_audio"] is True
    assert speech_status("stt")["configured"] is False
