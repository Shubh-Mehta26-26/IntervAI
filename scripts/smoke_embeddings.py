"""Check the configured embedding adapter with synthetic text and no stored records.

Run from the repository root with PYTHONPATH=backend. Never prints credentials,
request headers, provider response bodies, or embedding vectors.
"""

import asyncio
import json
import math

import httpx
from app.providers.embeddings import (
    EmbeddingError,
    embedding_status,
    get_embedding_provider,
)


async def main() -> int:
    ready, provider_name, model, _ = embedding_status()
    print(json.dumps({"provider": provider_name, "model": model, "configured": ready}))
    if not ready:
        return 2
    provider = get_embedding_provider()
    try:
        documents = await provider.embed_documents(
            [
                "An atomic transaction commits every operation or rolls them all back.",
                "A database index can speed up selective lookups.",
            ]
        )
        query = await provider.embed_query("What does atomicity mean in a transaction?")
    except EmbeddingError as exc:
        cause = exc.__cause__
        result = {"status": "FAILED", "error": exc.code}
        if isinstance(cause, httpx.HTTPStatusError):
            result["http_status"] = cause.response.status_code
        elif isinstance(cause, httpx.RequestError):
            result["transport_error"] = type(cause).__name__
        print(json.dumps(result))
        return 1
    vectors = [*documents, query]
    if len(documents) != 2 or any(
        len(vector) != provider.dimensions or not all(math.isfinite(value) for value in vector)
        for vector in vectors
    ):
        print(json.dumps({"status": "FAILED", "error": "invalid_vector_shape"}))
        return 1
    print(json.dumps({"status": "PASSED", "dimensions": provider.dimensions, "vectors": len(vectors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
