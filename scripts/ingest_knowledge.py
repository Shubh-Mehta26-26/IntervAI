"""Ingest a UTF-8 Markdown/text source into the versioned pgvector knowledge base."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionFactory, engine
from app.providers.embeddings import get_embedding_provider
from app.services.knowledge import ingest_document, read_source


def inputs(path: Path):
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.suffix.lower() in {".md", ".txt"})
    raise ValueError("Path does not exist.")


async def main(args):
    provider = get_embedding_provider()
    outcomes = []
    try:
        for path in inputs(args.path.resolve()):
            text = read_source(path)
            title = args.title or next(
                (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")),
                path.stem.replace("-", " ").title(),
            )
            async with SessionFactory() as db:
                document, changed = await ingest_document(
                    db,
                    provider,
                    title=title,
                    source=args.source or f"intervai://curated/{path.name}",
                    source_type=args.source_type,
                    domain=args.domain or path.stem.split("-")[0],
                    topic=args.topic or path.stem.replace("-", " "),
                    text=text,
                    metadata={"provenance": args.provenance},
                )
            outcomes.append({"id": str(document.id), "source": document.source, "changed": changed})
        print(json.dumps(outcomes, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--source")
    parser.add_argument("--source-type", default="curated")
    parser.add_argument("--domain")
    parser.add_argument("--topic")
    parser.add_argument(
        "--provenance",
        default="Project-authored technical reference, reviewed for the IntervAI curated corpus.",
    )
    asyncio.run(
        main(parser.parse_args()),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )
