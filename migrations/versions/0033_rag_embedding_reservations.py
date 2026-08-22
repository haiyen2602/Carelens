"""Add durable OpenAI embedding reservations and staged responses.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-18

The registry/checkpoint pair added in 0032 (originally authored as 0030, see
its own docstring) is insufficient when a process dies after a provider
response but before its checkpoint transaction.  This ledger reserves the
complete deterministic batch before the request and stages a validated
response before applying it, preventing automatic paid re-embedding.

BUILD-24Q renumbering (2026-08-21): originally revision 0031 -- see
report 52-build-24q-main-branch-reconciliation.md. No change to DDL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_embedding_reservation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("corpus_version", sa.String(), nullable=False),
        sa.Column("batch_key", sa.String(), nullable=False),
        sa.Column("chunk_keys", sa.JSON(), nullable=False),
        sa.Column("planned_token_ceiling", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider_request_id", sa.String(), nullable=True, unique=True),
        sa.Column("provider_input_tokens", sa.Integer(), nullable=True),
        sa.Column("response_embeddings", sa.JSON(), nullable=True),
        sa.Column("response_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounted_in_corpus", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reconciliation_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("corpus_version", "batch_key", name="uq_rag_embedding_reservation_batch"),
    )
    op.create_index(
        "ix_rag_embedding_reservation_corpus_status",
        "rag_embedding_reservation",
        ["corpus_version", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_embedding_reservation_corpus_status", table_name="rag_embedding_reservation")
    op.drop_table("rag_embedding_reservation")
