from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.identity import Base, Record

EMBEDDING_DIMENSIONS = 1536


class KnowledgeDocument(Record, Base):
    __tablename__ = "knowledge_documents"
    title: Mapped[str] = mapped_column(String(240))
    source: Mapped[str] = mapped_column(String(500), unique=True)
    source_type: Mapped[str] = mapped_column(String(40), default="curated")
    domain: Mapped[str] = mapped_column(String(120), index=True)
    topic: Mapped[str] = mapped_column(String(160), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="ready", index=True)
    embedding_provider: Mapped[str] = mapped_column(String(40))
    embedding_model: Mapped[str] = mapped_column(String(120))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        CheckConstraint("status IN ('ingesting','ready','failed')", name="ck_knowledge_status"),
        CheckConstraint("embedding_dimensions = 1536", name="ck_knowledge_dimensions"),
    )


class KnowledgeChunk(Record, Base):
    __tablename__ = "knowledge_chunks"
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(240))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunk_ordinal"),
        CheckConstraint("ordinal > 0", name="ck_knowledge_chunk_ordinal"),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class RetrievalLog(Record, Base):
    __tablename__ = "retrieval_logs"
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_evaluations.id", ondelete="CASCADE"), unique=True
    )
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_answers.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSONB)
    results: Mapped[list] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    retrieval_version: Mapped[str] = mapped_column(String(40))


class EvaluationSource(Record, Base):
    __tablename__ = "evaluation_sources"
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer_evaluations.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="RESTRICT"), index=True
    )
    retrieval_rank: Mapped[int] = mapped_column(Integer)
    similarity: Mapped[float]
    relationship: Mapped[str] = mapped_column(String(20))
    supported_claim: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("evaluation_id", "chunk_id", name="uq_evaluation_source_chunk"),
        CheckConstraint("retrieval_rank > 0", name="ck_evaluation_source_rank"),
        CheckConstraint(
            "relationship IN ('supports','contradicts','insufficient')",
            name="ck_evaluation_source_relationship",
        ),
    )
