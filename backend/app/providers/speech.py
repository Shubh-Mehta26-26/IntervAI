"""Real adapters only. Tests inject providers; no production mock registry."""

import asyncio
import io
import json
import shutil
import struct
import subprocess
import sys
import wave
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import get_settings


class SpeechError(RuntimeError):
    code = "speech_failed"


class SpeechConfigurationError(SpeechError):
    code = "speech_not_configured"


class SpeechSegment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    word: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=2000)
    conf: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_timing(self):
        if self.end < self.start:
            raise ValueError("Invalid speech segment timing")
        return self


class Transcript(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=12000)
    language: str | None = None
    segments: list[SpeechSegment] = Field(default_factory=list, max_length=5000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SpeechToTextProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def transcribe(self, audio: bytes) -> Transcript: ...


class TextToSpeechProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def synthesize(self, text: str) -> bytes: ...


async def subprocess_output(args, data, timeout):
    def execute():
        try:
            result = subprocess.run(
                args,
                input=data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if len(result.stdout) > 12 * 1024 * 1024:
                raise SpeechError("Speech provider output exceeded the limit.")
            return result.stdout
        except (subprocess.SubprocessError, OSError) as exc:
            raise SpeechError(
                "Speech processing failed. You can type your answer instead."
            ) from exc

    return await asyncio.to_thread(execute)


class VoskProvider(SpeechToTextProvider):
    name = "vosk"

    def __init__(self, path: Path, timeout: int):
        self.path, self.timeout, self.model = path, timeout, path.name

    async def transcribe(self, audio):
        # Separate process enforces a real deadline, including model loading. No auto downloads.
        output = await subprocess_output(
            [sys.executable, "-m", "app.providers.vosk_runner", str(self.path)], audio, self.timeout
        )
        return Transcript.model_validate_json(output)


class EspeakProvider(TextToSpeechProvider):
    name, model = "espeak", "espeak-ng"

    async def synthesize(self, text):
        s = get_settings()
        audio = await subprocess_output(
            [
                s.espeak_executable,
                "--stdout",
                "--stdin",
                "-v",
                s.tts_voice,
                "-s",
                str(round(175 * s.tts_speed)),
            ],
            text.encode(),
            s.speech_timeout_seconds,
        )
        # eSpeak stdout has placeholder stream lengths; finalize this bounded PCM file.
        if len(audio) >= 44 and audio[:4] == b"RIFF" and audio[36:40] == b"data":
            value = bytearray(audio)
            struct.pack_into("<I", value, 4, len(value) - 8)
            struct.pack_into("<I", value, 40, len(value) - 44)
            return bytes(value)
        raise SpeechError("Local speech provider returned invalid audio.")


class OpenAISpeech:
    name = "openai"

    def __init__(self, model, key):
        self.model, self.key = model, key

    async def request(self, endpoint, **kwargs):
        s = get_settings()
        try:
            async with httpx.AsyncClient(timeout=s.speech_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{s.llm_base_url.rstrip('/')}/audio/{endpoint}",
                    headers={"Authorization": f"Bearer {self.key}"},
                    **kwargs,
                ) as response:
                    response.raise_for_status()
                    parts, size = [], 0
                    async for part in response.aiter_bytes():
                        size += len(part)
                        if size > 12 * 1024 * 1024:
                            raise SpeechError("Speech provider output exceeded the limit.")
                        parts.append(part)
                    return b"".join(parts)
        except httpx.HTTPError as exc:
            raise SpeechError(
                "Speech provider request failed. You can type your answer instead."
            ) from exc


class OpenAISTT(OpenAISpeech, SpeechToTextProvider):
    async def transcribe(self, audio):
        raw = await self.request(
            "transcriptions",
            data={
                "model": self.model,
                "response_format": "json",
                "language": get_settings().speech_language,
            },
            files={"file": ("answer.wav", audio, "audio/wav")},
        )
        try:
            payload = json.loads(raw)
            return Transcript(text=payload["text"], language=payload.get("language"))
        except (ValueError, KeyError, TypeError) as exc:
            raise SpeechError("Speech provider returned an invalid transcript.") from exc


class OpenAITTS(OpenAISpeech, TextToSpeechProvider):
    async def synthesize(self, text):
        s = get_settings()
        return await self.request(
            "speech",
            json={
                "model": self.model,
                "input": text,
                "voice": s.tts_voice,
                "speed": s.tts_speed,
                "response_format": "wav",
            },
        )


def speech_status(kind):
    s = get_settings()
    provider = getattr(s, f"{kind}_provider")
    model = getattr(s, f"{kind}_model")
    key = getattr(s, f"{kind}_api_key") or s.openai_api_key
    if provider == "openai":
        ready = bool(model and key and key.get_secret_value())
    elif kind == "stt" and provider == "vosk":
        import importlib.util

        ready = bool(
            s.vosk_model_path
            and (s.vosk_model_path / "am/final.mdl").is_file()
            and (s.vosk_model_path / "conf/model.conf").is_file()
            and importlib.util.find_spec("vosk")
        )
    elif kind == "tts" and provider == "espeak":
        ready = bool(shutil.which(s.espeak_executable))
    else:
        ready = False
    return {
        "configured": ready,
        "provider": provider or None,
        "message": "Speech provider is available."
        if ready
        else "Voice unavailable. You can type your answer instead.",
    }


def get_stt():
    if not speech_status("stt")["configured"]:
        raise SpeechConfigurationError("Voice unavailable. You can type your answer instead.")
    s = get_settings()
    if s.stt_provider == "vosk":
        return VoskProvider(s.vosk_model_path, s.speech_timeout_seconds)
    return OpenAISTT(s.stt_model, (s.stt_api_key or s.openai_api_key).get_secret_value())


def get_tts():
    if not speech_status("tts")["configured"]:
        raise SpeechConfigurationError("Voice unavailable. You can type your answer instead.")
    s = get_settings()
    if s.tts_provider == "espeak":
        return EspeakProvider()
    return OpenAITTS(s.tts_model, (s.tts_api_key or s.openai_api_key).get_secret_value())


def wav_info(audio, max_seconds=180, *, input_audio=True):
    try:
        if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise ValueError("Not WAV")
        with wave.open(io.BytesIO(audio)) as file:
            rate, frames = file.getframerate(), file.getnframes()
            if file.getnchannels() != 1 or file.getsampwidth() != 2 or file.getcomptype() != "NONE":
                raise ValueError("Expected mono PCM16")
            if rate not in ({16000} if input_audio else {16000, 22050, 24000, 44100, 48000}):
                raise ValueError("Unsupported sample rate")
            duration = frames / rate
            data = file.readframes(frames)
            if not 0.1 <= duration <= max_seconds or len(data) != frames * 2:
                raise ValueError("Invalid duration")
            return {"duration_seconds": duration, "sample_rate": rate, "bytes": len(audio)}, data
    except (wave.Error, EOFError, ValueError, ZeroDivisionError) as exc:
        raise SpeechError(
            "Use a valid mono 16 kHz PCM WAV recording within the duration limit."
        ) from exc
