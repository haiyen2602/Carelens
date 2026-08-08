"""Phase 1: extensions (vector, pg_trgm, unaccent) + drug_chunks + audit_log

Xem specs/build-kickoff-prompt.md Phase 1 va specs/chatbot-rag-design.md
muc 3.1 (drug_chunks), muc 5.2 (audit_log).

Revision ID: 0001
Revises:
Create Date: 2026-08-08

"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536  # text-embedding-3-small


def upgrade() -> None:
    # --- Extensions (ADR-0008: pgvector; chatbot-rag-design.md muc 2: pg_trgm + unaccent) ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # --- drug_chunks ---
    op.create_table(
        "drug_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_id", sa.String(), nullable=False),
        sa.Column("danh_muc", sa.String(), nullable=False),
        sa.Column("muc_nghiem_trong", sa.String(), nullable=False),
        sa.Column("field_group", sa.String(), nullable=False),
        sa.Column("noi_dung", sa.Text(), nullable=False),
        sa.Column("noi_dung_unaccent", sa.Text(), nullable=False),
        sa.Column("ten_thuoc_unaccent", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drug_chunks_drug_id", "drug_chunks", ["drug_id"])
    op.create_index("ix_drug_chunks_drug_id_field_group", "drug_chunks", ["drug_id", "field_group"])

    # HNSW index cho cosine similarity search (chatbot-rag-design.md muc 4.2: vector search
    # dung cosine). SQLAlchemy khong co API tao HNSW truc tiep nen dung raw SQL.
    op.execute(
        "CREATE INDEX ix_drug_chunks_embedding_hnsw ON drug_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # GIN trigram index tren cot DA BO DAU (mucd 4.2: bat buoc unaccent truoc khi index/query,
    # tranh trigram tren co dau vs khong dau khong overlap).
    op.execute(
        "CREATE INDEX ix_drug_chunks_noi_dung_unaccent_trgm ON drug_chunks "
        "USING gin (noi_dung_unaccent gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_drug_chunks_ten_thuoc_unaccent_trgm ON drug_chunks "
        "USING gin (ten_thuoc_unaccent gin_trgm_ops)"
    )

    # --- audit_log (APPEND-ONLY, BR-7.5 - khong duoc UPDATE/DELETE tu code ung dung) ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("dose_event_id", sa.String(), nullable=True),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("final_response", sa.Text(), nullable=False),
        sa.Column("total_duration_ms", sa.Float(), nullable=False),
    )
    op.create_index("ix_audit_log_patient_id", "audit_log", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_patient_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.execute("DROP INDEX IF EXISTS ix_drug_chunks_ten_thuoc_unaccent_trgm")
    op.execute("DROP INDEX IF EXISTS ix_drug_chunks_noi_dung_unaccent_trgm")
    op.execute("DROP INDEX IF EXISTS ix_drug_chunks_embedding_hnsw")
    op.drop_index("ix_drug_chunks_drug_id_field_group", table_name="drug_chunks")
    op.drop_index("ix_drug_chunks_drug_id", table_name="drug_chunks")
    op.drop_table("drug_chunks")

    # Khong drop extension luc downgrade - co the co object khac dang dung chung
    # (an toan hon la giu lai, chi rollback schema cua migration nay).
