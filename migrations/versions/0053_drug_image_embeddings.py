"""Persist versioned OpenCLIP reference-image embeddings.

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug_image_embedding",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("drug_image_id", sa.String(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_version", sa.String(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("preprocessing_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("embedding_dimension = 512", name="ck_drug_image_embedding_dimension"),
        sa.ForeignKeyConstraint(["drug_image_id"], ["drug_image.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "drug_image_id",
            "embedding_model",
            "embedding_version",
            name="uq_drug_image_embedding_model_version",
        ),
    )
    # At 3,543 references, an exact cosine scan is both simpler and the
    # measured baseline.  Do not create ANN indexes before they are justified.
    op.create_index(
        "ix_drug_image_embedding_model_version",
        "drug_image_embedding",
        ["embedding_model", "embedding_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_drug_image_embedding_model_version", table_name="drug_image_embedding")
    op.drop_table("drug_image_embedding")
