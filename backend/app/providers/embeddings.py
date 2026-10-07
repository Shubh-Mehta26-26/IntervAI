import math
from abc import ABC, abstractmethod
from urllib.parse import quote

import httpx

from app.core.config import get_settings


class EmbeddingError(RuntimeError):
    code = "embedding_failed"


class EmbeddingConfigurationError(EmbeddingError):
    code = "embedding_not_configured"


class EmbeddingRateLimitError(EmbeddingError):
    code = "embedding_rate_limited"


class EmbeddingProvider(ABC):
    name: str
    model: str
    dimensions: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, dimensions: int, base_url: str, timeout: int):
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "input": texts,
                        "encoding_format": "float",
                        "dimensions": self.dimensions,
                    },
                )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in data]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise EmbeddingRateLimitError(
                    "The embedding provider is temporarily rate limited. Retrying shortly."
                ) from exc
            raise EmbeddingError("The embedding provider request failed.") from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError("The embedding provider request failed.") from exc
        if len(vectors) != len(texts) or any(
            not isinstance(vector, list)
            or len(vector) != self.dimensions
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise EmbeddingError("The embedding provider returned an invalid vector shape.")
        return vectors


class GeminiEmbeddingProvider(EmbeddingProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, dimensions: int, timeout: int):
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout = timeout
        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(model, safe="")
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "SEMANTIC_SIMILARITY")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        config = {"taskType": task_type, "outputDimensionality": self.dimensions}

        def content(text: str) -> dict:
            return {"parts": [{"text": text}]}

        if len(texts) == 1:
            endpoint = ":embedContent"
            body = {
                "model": f"models/{self.model}",
                "content": content(texts[0]),
                "embedContentConfig": config,
            }
        else:
            endpoint = ":batchEmbedContents"
            body = {
                "requests": [
                    {
                        "model": f"models/{self.model}",
                        "content": content(text),
                        "embedContentConfig": config,
                    }
                    for text in texts
                ]
            }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url + endpoint,
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                )
            response.raise_for_status()
            payload = response.json()
            vectors = (
                [payload["embedding"]["values"]]
                if len(texts) == 1
                else [item["values"] for item in payload["embeddings"]]
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise EmbeddingRateLimitError(
                    "The embedding provider is temporarily rate limited. Retrying shortly."
                ) from exc
            raise EmbeddingError("The embedding provider request failed.") from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError("The embedding provider request failed.") from exc
        if len(vectors) != len(texts) or any(
            not isinstance(vector, list)
            or len(vector) != self.dimensions
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise EmbeddingError("The embedding provider returned an invalid vector shape.")
        return vectors


def embedding_status() -> tuple[bool, str | None, str | None, str]:
    settings = get_settings()
    provider = settings.embedding_provider.strip().lower()
    if provider not in {"gemini", "openai", ""}:
        return False, provider, settings.embedding_model or None, f"Unsupported embedding provider: {provider}."
    secret = settings.gemini_api_key if provider == "gemini" else settings.openai_api_key
    key = secret.get_secret_value() if secret else ""
    key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    missing = [
        name
        for name, value in (
            ("EMBEDDING_PROVIDER", provider),
            ("EMBEDDING_MODEL", settings.embedding_model),
            (key_name, key),
        )
        if not value
    ]
    if missing:
        return False, provider or None, settings.embedding_model or None, (
            "Configure " + ", ".join(missing) + " for grounded evaluation."
        )
    if settings.embedding_dimensions != 1536:
        return False, provider, settings.embedding_model, "This database requires EMBEDDING_DIMENSIONS=1536."
    return True, provider, settings.embedding_model, "The embedding provider is configured."


def get_embedding_provider() -> EmbeddingProvider:
    ready, provider, model, message = embedding_status()
    if not ready:
        raise EmbeddingConfigurationError(message)
    settings = get_settings()
    if provider == "gemini":
        return GeminiEmbeddingProvider(
            settings.gemini_api_key.get_secret_value(),
            model,
            settings.embedding_dimensions,
            settings.llm_timeout_seconds,
        )
    return OpenAIEmbeddingProvider(
        settings.openai_api_key.get_secret_value(),
        model,
        settings.embedding_dimensions,
        settings.llm_base_url,
        settings.llm_timeout_seconds,
    )
