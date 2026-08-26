"""Add traceable storage metadata for validated drug reference images.

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug_image",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("drug_product_id", sa.String(), nullable=False),
        sa.Column("legacy_drug_id", sa.String(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_page_url", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.String(), nullable=False),
        sa.Column("source_product_id", sa.String(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalized_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("view_type", sa.String(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation_status", sa.String(), nullable=False),
        sa.Column("collection_version", sa.String(), nullable=False),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "validation_status IN ('VALIDATED', 'INVALID', 'RETIRED')", name="ck_drug_image_validation_status"
        ),
        sa.CheckConstraint("width > 0 AND height > 0 AND file_size > 0", name="ck_drug_image_dimensions"),
        sa.ForeignKeyConstraint(["drug_product_id"], ["drug_product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint(
            "drug_product_id",
            "source_snapshot_id",
            "source_url",
            "checksum_sha256",
            "view_type",
            name="uq_drug_image_source_identity",
        ),
    )
    op.create_index("ix_drug_image_drug_product_id", "drug_image", ["drug_product_id"])
    op.create_index("ix_drug_image_checksum_sha256", "drug_image", ["checksum_sha256"])
    op.create_index("ix_drug_image_product_status", "drug_image", ["drug_product_id", "validation_status"])
    op.create_index(
        "uq_drug_image_validated_primary",
        "drug_image",
        ["drug_product_id", "collection_version"],
        unique=True,
        postgresql_where=sa.text("is_primary AND validation_status = 'VALIDATED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_drug_image_validated_primary", table_name="drug_image")
    op.drop_index("ix_drug_image_product_status", table_name="drug_image")
    op.drop_index("ix_drug_image_checksum_sha256", table_name="drug_image")
    op.drop_index("ix_drug_image_drug_product_id", table_name="drug_image")
    op.drop_table("drug_image")
