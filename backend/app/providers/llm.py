import json
from abc import ABC, abstractmethod
from typing import TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    code = "llm_failed"


class LLMConfigurationError(LLMError):
    code = "llm_not_configured"


class LLMOutputError(LLMError):
    code = "llm_invalid_output"


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def structured(self, *, system: str, user: str, schema: type[T], name: str) -> T:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self.api_key, self.model = api_key, model
        self.base_url, self.timeout = base_url.rstrip("/"), timeout

    async def structured(self, *, system: str, user: str, schema: type[T], name: str) -> T:
        output_schema = strict_json_schema(schema.model_json_schema())
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "developer", "content": system},
                {"role": "user", "content": user},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "strict": True,
                    "schema": output_schema,
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError("The AI provider request failed. Try again shortly.") from exc
        if payload.get("status") != "completed":
            raise LLMError("The AI provider did not complete the request.")
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise LLMOutputError("The AI provider refused this interview operation.")
                if content.get("type") == "output_text":
                    try:
                        return schema.model_validate(json.loads(content["text"]))
                    except (KeyError, ValueError) as exc:
                        raise LLMOutputError(
                            "The AI provider returned invalid structured output."
                        ) from exc
        raise LLMOutputError("The AI provider returned no structured output.")


def strict_json_schema(value):
    """Normalize Pydantic JSON Schema for strict Structured Outputs."""
    if isinstance(value, dict):
        value = {key: strict_json_schema(item) for key, item in value.items()}
        if value.get("type") == "object" or "properties" in value:
            properties = value.get("properties", {})
            value["additionalProperties"] = False
            value["required"] = list(properties)
        return value
    if isinstance(value, list):
        return [strict_json_schema(item) for item in value]
    return value


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: int):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    async def structured(self, *, system: str, user: str, schema: type[T], name: str) -> T:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    + quote(self.model, safe="")
                    + ":generateContent",
                    headers={"x-goog-api-key": self.api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "responseJsonSchema": schema.model_json_schema(),
                        },
                    },
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError("The AI provider request failed. Try again shortly.") from exc
        try:
            candidate = payload["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Incomplete output")
            text = "".join(
                p["text"]
                for p in candidate["content"]["parts"]
                if "text" in p and not p.get("thought")
            )
            return schema.model_validate(json.loads(text))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise LLMOutputError("The AI provider returned invalid structured output.") from exc


def provider_status() -> tuple[bool, str | None, str | None, str]:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    secret = (
        settings.gemini_api_key
        if provider == "gemini"
        else settings.openai_api_key or settings.llm_api_key
    )
    model = (
        settings.gemini_model if provider == "gemini" else settings.openai_model
    ) or settings.llm_model
    key = secret.get_secret_value() if secret else ""
    if provider not in {"gemini", "openai"}:
        return False, provider or None, model or None, "Choose LLM_PROVIDER=gemini or openai."
    if not model or not key:
        return (
            False,
            provider or None,
            model or None,
            (
                "Configure GEMINI_MODEL and GEMINI_API_KEY to start an interview."
                if provider == "gemini"
                else "Configure OPENAI_MODEL (or LLM_MODEL) and OPENAI_API_KEY to start an interview."
            ),
        )
    return True, provider, model, "The interview AI provider is configured."


def get_provider() -> LLMProvider:
    ready, provider, model, message = provider_status()
    if not ready:
        raise LLMConfigurationError(message)
    settings = get_settings()
    if provider == "gemini":
        return GeminiProvider(
            settings.gemini_api_key.get_secret_value(), model, settings.llm_timeout_seconds
        )
    return OpenAIProvider(
        (settings.openai_api_key or settings.llm_api_key).get_secret_value(),
        model,
        settings.llm_base_url,
        settings.llm_timeout_seconds,
    )
