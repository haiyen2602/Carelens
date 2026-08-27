"""Persist B-07's server-issued drug-image candidate lifecycle.

The table intentionally stores only identifiers, outcome/version, an
allowlisted candidate-action snapshot, and confirmation lifecycle metadata.
It never stores patient image bytes, OCR text, embedding vectors, or storage
paths.  This is required to reject stale/forged confirmations across requests
and workers without turning an unconfirmed visual result into a drug entity.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug_recognition_attempt",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("recognition_version", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("requested_attribute", sa.String(), nullable=True),
        sa.Column("selected_drug_product_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('AWAITING_CONFIRMATION', 'INSUFFICIENT_EVIDENCE', 'CONFIRMED', 'SUPERSEDED', 'EXPIRED', 'FAILED')",
            name="ck_drug_recognition_attempt_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drug_recognition_attempt_conversation_id", "drug_recognition_attempt", ["conversation_id"])
    op.create_index("ix_drug_recognition_attempt_patient_id", "drug_recognition_attempt", ["patient_id"])
    op.create_index("ix_drug_recognition_attempt_actor_id", "drug_recognition_attempt", ["actor_id"])
    op.create_index("ix_drug_recognition_attempt_status", "drug_recognition_attempt", ["status"])
    op.create_index("ix_drug_recognition_attempt_expires_at", "drug_recognition_attempt", ["expires_at"])
    op.create_index(
        "ix_drug_recognition_attempt_scope_status",
        "drug_recognition_attempt",
        ["conversation_id", "patient_id", "actor_id", "status"],
    )
    op.create_table(
        "doctor_review_image_attachment",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("handoff_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("file_size > 0", name="ck_doctor_review_image_attachment_file_size"),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_doctor_review_image_attachment_mime_type",
        ),
        sa.ForeignKeyConstraint(["handoff_id"], ["doctor_review_request.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["doctor_review_message.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_doctor_review_image_attachment_handoff_id", "doctor_review_image_attachment", ["handoff_id"])
    op.create_index("ix_doctor_review_image_attachment_patient_id", "doctor_review_image_attachment", ["patient_id"])
    op.create_index("ix_doctor_review_image_attachment_expires_at", "doctor_review_image_attachment", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_doctor_review_image_attachment_expires_at", table_name="doctor_review_image_attachment")
    op.drop_index("ix_doctor_review_image_attachment_patient_id", table_name="doctor_review_image_attachment")
    op.drop_index("ix_doctor_review_image_attachment_handoff_id", table_name="doctor_review_image_attachment")
    op.drop_table("doctor_review_image_attachment")
    op.drop_index("ix_drug_recognition_attempt_scope_status", table_name="drug_recognition_attempt")
    op.drop_index("ix_drug_recognition_attempt_expires_at", table_name="drug_recognition_attempt")
    op.drop_index("ix_drug_recognition_attempt_status", table_name="drug_recognition_attempt")
    op.drop_index("ix_drug_recognition_attempt_actor_id", table_name="drug_recognition_attempt")
    op.drop_index("ix_drug_recognition_attempt_patient_id", table_name="drug_recognition_attempt")
    op.drop_index("ix_drug_recognition_attempt_conversation_id", table_name="drug_recognition_attempt")
    op.drop_table("drug_recognition_attempt")
