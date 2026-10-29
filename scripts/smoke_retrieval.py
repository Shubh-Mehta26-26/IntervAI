"""Verify configured embeddings retrieve a project-authored source without user data."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionFactory, engine  # noqa: E402
from app.providers.embeddings import (  # noqa: E402
    EmbeddingError,
    get_embedding_provider,
)
from app.services.knowledge import retrieve  # noqa: E402


async def main() -> int:
    provider = get_embedding_provider()
    try:
        try:
            async with SessionFactory() as db:
                _, matches = await retrieve(
                    db,
                    provider,
                    question=SimpleNamespace(
                        topic="DBMS",
                        skill="Transactions",
                        text="What does atomicity mean for a database transaction?",
                    ),
                    answer=SimpleNamespace(text="Every operation commits or all operations roll back."),
                )
        except EmbeddingError as exc:
            print(json.dumps({"status": "FAILED", "error": exc.code}))
            return 1
        sources = [item.source for item in matches]
        passed = "intervai://curated/dbms-transactions.md" in sources
        print(json.dumps({"status": "PASSED" if passed else "FAILED", "sources": sources}))
        return 0 if passed else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(
        asyncio.run(
            main(),
            loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
        )
    )
