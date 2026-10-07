"""Phase 5 grounded RAG.

Revision ID: 7b31d944be52
Revises: 1acbf47bc035
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "7b31d944be52"
down_revision: str | None = "1acbf47bc035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "answer_evaluations",
        sa.Column("grounding_status", sa.String(24), nullable=False, server_default="insufficient"),
    )
    op.add_column(
        "answer_evaluations",
        sa.Column("evaluation_notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_check_constraint(
        "ck_evaluation_grounding",
        "answer_evaluations",
        "grounding_status IN ('grounded','insufficient')",
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("domain", sa.String(120), nullable=False),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("embedding_provider", sa.String(40), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source"),
        sa.CheckConstraint("status IN ('ingesting','ready','failed')", name="ck_knowledge_status"),
        sa.CheckConstraint("embedding_dimensions = 1536", name="ck_knowledge_dimensions"),
    )
    op.create_index("ix_knowledge_documents_domain", "knowledge_documents", ["domain"])
    op.create_index("ix_knowledge_documents_topic", "knowledge_documents", ["topic"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
    op.create_index("ix_knowledge_documents_checksum", "knowledge_documents", ["checksum"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section", sa.String(240), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunk_ordinal"),
        sa.CheckConstraint("ordinal > 0", name="ck_knowledge_chunk_ordinal"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "retrieval_logs",
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("retrieval_version", sa.String(40), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evaluation_id"], ["answer_evaluations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["answer_id"], ["interview_answers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id"),
    )
    op.create_index("ix_retrieval_logs_interview_id", "retrieval_logs", ["interview_id"])
    op.create_index("ix_retrieval_logs_answer_id", "retrieval_logs", ["answer_id"])
    op.create_table(
        "evaluation_sources",
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("supported_claim", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evaluation_id"], ["answer_evaluations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "chunk_id", name="uq_evaluation_source_chunk"),
        sa.CheckConstraint("retrieval_rank > 0", name="ck_evaluation_source_rank"),
        sa.CheckConstraint("relationship IN ('supports','contradicts','insufficient')", name="ck_evaluation_source_relationship"),
    )
    op.create_index("ix_evaluation_sources_evaluation_id", "evaluation_sources", ["evaluation_id"])
    op.create_index("ix_evaluation_sources_chunk_id", "evaluation_sources", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("evaluation_sources")
    op.drop_table("retrieval_logs")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_constraint("ck_evaluation_grounding", "answer_evaluations", type_="check")
    op.drop_column("answer_evaluations", "evaluation_notes")
    op.drop_column("answer_evaluations", "grounding_status")
