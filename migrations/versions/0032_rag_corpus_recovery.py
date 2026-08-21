"""Add reproducible pgvector-corpus registry and recovery checkpoints.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-18

Existing legacy chunks are intentionally left nullable/unmodified.  New corpus
rows use a logical chunk key and checkpoint state so an interrupted embedding
run can resume without duplicate rows or requests.

BUILD-24Q renumbering (2026-08-21): originally authored as revision 0030,
chaining directly onto 0029. Renumbered to 0032 (down_revision 0031) to
reconcile with `main`'s own 0030 (nudge) / 0031 (remove_better_auth_and_add_
supabase_uid), which collided on the same revision IDs after the two
branches diverged -- see report 52-build-24q-main-branch-reconciliation.md.
No change to this migration's actual DDL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create additive corpus metadata and idempotency storage."""

    op.add_column("drug_chunks", sa.Column("corpus_version", sa.String(), nullable=True))
    op.add_column("drug_chunks", sa.Column("chunk_key", sa.String(), nullable=True))
    op.add_column("drug_chunks", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("drug_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.create_index("ix_drug_chunks_corpus_version", "drug_chunks", ["corpus_version"])
    op.create_index(
        "uq_drug_chunks_corpus_chunk_key",
        "drug_chunks",
        ["corpus_version", "chunk_key"],
        unique=True,
        postgresql_where=sa.text("corpus_version IS NOT NULL AND chunk_key IS NOT NULL"),
    )

    op.create_table(
        "rag_corpus",
        sa.Column("corpus_version", sa.String(), primary_key=True),
        sa.Column("source_manifest_hash", sa.String(), nullable=False),
        sa.Column("chunk_manifest_hash", sa.String(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("index_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expected_chunks", sa.Integer(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("actual_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rag_corpus_checkpoint",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("corpus_version", sa.String(), nullable=False),
        sa.Column("chunk_key", sa.String(), nullable=False),
        sa.Column("drug_chunk_id", sa.String(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("batch_number", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_version", "chunk_key", name="uq_rag_corpus_checkpoint_key"),
    )
    op.create_index(
        "ix_rag_corpus_checkpoint_corpus_version",
        "rag_corpus_checkpoint",
        ["corpus_version"],
    )
    op.create_index(
        "ix_rag_corpus_checkpoint_status",
        "rag_corpus_checkpoint",
        ["corpus_version", "status"],
    )


def downgrade() -> None:
    """Remove BUILD-7C-only tables and additive metadata."""

    op.drop_index("ix_rag_corpus_checkpoint_status", table_name="rag_corpus_checkpoint")
    op.drop_index("ix_rag_corpus_checkpoint_corpus_version", table_name="rag_corpus_checkpoint")
    op.drop_table("rag_corpus_checkpoint")
    op.drop_table("rag_corpus")
    op.drop_index("uq_drug_chunks_corpus_chunk_key", table_name="drug_chunks")
    op.drop_index("ix_drug_chunks_corpus_version", table_name="drug_chunks")
    op.drop_column("drug_chunks", "embedding_dimensions")
    op.drop_column("drug_chunks", "embedding_model")
    op.drop_column("drug_chunks", "chunk_key")
    op.drop_column("drug_chunks", "corpus_version")
