import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.providers.embeddings import EmbeddingProvider

RETRIEVAL_VERSION = "rag-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
ALLOWED_SUFFIXES = {".md", ".txt"}


class KnowledgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    section: str | None
    content_hash: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    title: str
    source: str
    domain: str
    topic: str
    content: str
    rank: int
    similarity: float

    def prompt_value(self):
        return {
            "knowledge_chunk_id": str(self.chunk_id),
            "title": self.title,
            "source": self.source,
            "content": self.content,
            "rank": self.rank,
            "similarity": round(self.similarity, 6),
        }

    def log_value(self):
        return {
            "knowledge_chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "rank": self.rank,
            "similarity": round(self.similarity, 6),
        }


def read_source(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise KnowledgeError("Source must be a regular .md or .txt file.")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise KnowledgeError("Source exceeds the 2 MiB ingestion limit.")
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeError("Source must be valid UTF-8 text.") from exc
    value = value.replace("\x00", "").replace("\r\n", "\n").strip()
    if len(value) < 80:
        raise KnowledgeError("Source is too short to create useful knowledge chunks.")
    return value


def chunk_text(text: str, target=1400, overlap=180) -> list[ChunkDraft]:
    blocks = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    result: list[ChunkDraft] = []
    section = None
    current = ""
    for block in blocks:
        heading = re.match(r"^#{1,4}\s+(.{1,240})$", block)
        if heading:
            section = heading.group(1).strip()
        candidate = f"{current}\n\n{block}".strip()
        if current and len(candidate) > target:
            content = current.strip()
            result.append(ChunkDraft(content, section, hashlib.sha256(content.encode()).hexdigest()))
            current = (content[-overlap:] + "\n\n" + block).strip()
        else:
            current = candidate
    if current:
        result.append(ChunkDraft(current, section, hashlib.sha256(current.encode()).hexdigest()))
    return result


async def ingest_document(
    db,
    provider: EmbeddingProvider,
    *,
    title: str,
    source: str,
    source_type: str,
    domain: str,
    topic: str,
    text: str,
    metadata: dict | None = None,
):
    settings = get_settings()
    if (
        not source.strip()
        or len(source) > 500
        or re.match(r"^[A-Za-z]:[\\/]", source)
        or source.startswith(("/", "\\", "../", "..\\"))
        or any(character in source for character in ("\x00", "\n", "\r"))
    ):
        raise KnowledgeError("Source must be a safe logical URI or identifier, not a file path.")
    if provider.dimensions != 1536 or settings.embedding_dimensions != 1536:
        raise KnowledgeError("This database revision requires EMBEDDING_DIMENSIONS=1536.")
    checksum = hashlib.sha256(text.encode()).hexdigest()
    existing = await db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source == source))
    if (
        existing
        and existing.checksum == checksum
        and existing.status == "ready"
        and existing.embedding_provider == provider.name
        and existing.embedding_model == provider.model
        and existing.embedding_dimensions == provider.dimensions
    ):
        return existing, False
    drafts = chunk_text(text)
    vectors: list[list[float]] = []
    for offset in range(0, len(drafts), settings.embedding_batch_size):
        vectors.extend(
            await provider.embed_documents([item.content for item in drafts[offset : offset + settings.embedding_batch_size]])
        )
    document = existing or KnowledgeDocument(source=source)
    document.title = title[:240]
    document.source_type = source_type[:40]
    document.domain = domain[:120]
    document.topic = topic[:160]
    document.metadata_ = metadata or {}
    document.checksum = checksum
    document.status = "ready"
    document.embedding_provider = provider.name
    document.embedding_model = provider.model
    document.embedding_dimensions = provider.dimensions
    document.error = None
    db.add(document)
    await db.flush()
    if existing:
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True), 1):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                ordinal=ordinal,
                content=draft.content,
                section=draft.section,
                metadata_={},
                content_hash=draft.content_hash,
                embedding=vector,
            )
        )
    await db.commit()
    await db.refresh(document)
    return document, True


def retrieval_query(question, answer) -> str:
    # Labels make the embedding input unambiguous; source text is data, never instructions.
    return (
        f"Technical topic: {question.topic}\n"
        f"Skill: {question.skill or question.topic}\n"
        f"Question: {question.text[:1800]}\n"
        f"Candidate answer claims: {answer.text[:3500]}"
    )


def validate_citations(evaluation, retrieved: list[RetrievedChunk]):
    allowed = {item.chunk_id for item in retrieved}
    cited = [item.knowledge_chunk_id for item in evaluation.knowledge_evidence]
    if len(cited) != len(set(cited)) or any(item not in allowed for item in cited):
        raise KnowledgeError("Evaluation cited a knowledge chunk that was not retrieved.")
    if evaluation.grounding_status == "grounded" and not cited:
        raise KnowledgeError("A grounded evaluation must cite retrieved knowledge.")
    if not retrieved and evaluation.grounding_status != "insufficient":
        raise KnowledgeError("An evaluation without retrieved knowledge must be insufficient.")


async def retrieve(db, provider: EmbeddingProvider, *, question, answer) -> tuple[str, list[RetrievedChunk]]:
    settings = get_settings()
    query = retrieval_query(question, answer)
    vector = await provider.embed_query(query)
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeDocument.status == "ready",
            KnowledgeDocument.embedding_provider == provider.name,
            KnowledgeDocument.embedding_model == provider.model,
            KnowledgeDocument.embedding_dimensions == provider.dimensions,
        )
        .order_by(distance)
        .limit(settings.retrieval_top_k)
    )
    rows = (await db.execute(statement)).all()
    result = []
    for chunk, document, raw_distance in rows:
        similarity = 1.0 - float(raw_distance)
        if similarity < settings.retrieval_min_similarity:
            continue
        result.append(
            RetrievedChunk(
                chunk.id,
                document.id,
                document.title,
                document.source,
                document.domain,
                document.topic,
                chunk.content,
                len(result) + 1,
                similarity,
            )
        )
    return query, result
