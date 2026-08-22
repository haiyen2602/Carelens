"""Add durable Agent V2 Doctor Handoff requests.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-18

The table is additive.  It captures only an auditable handoff boundary; it
does not replace the legacy escalation table or create provider delivery.

BUILD-24Q renumbering (2026-08-21): originally revision 0032 -- see
report 52-build-24q-main-branch-reconciliation.md. No change to DDL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctor_review_request",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("assigned_doctor_id", sa.String(), nullable=True),
        sa.Column("created_by_actor_id", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("risk_disposition", sa.String(), nullable=False),
        sa.Column("patient_question", sa.Text(), nullable=False),
        sa.Column("agent_summary", sa.Text(), nullable=False),
        sa.Column("summary_provenance", sa.JSON(), nullable=False),
        sa.Column("verified_context_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by_doctor_id", sa.String(), nullable=True),
        sa.Column("doctor_answer", sa.Text(), nullable=True),
    )
    op.create_index("uq_doctor_review_request_idempotency", "doctor_review_request", ["idempotency_key"], unique=True)
    op.create_index("ix_doctor_review_request_patient_status", "doctor_review_request", ["patient_id", "status"])
    op.create_index("ix_doctor_review_request_doctor_status", "doctor_review_request", ["assigned_doctor_id", "status"])
    op.create_index("ix_doctor_review_request_created", "doctor_review_request", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_doctor_review_request_created", table_name="doctor_review_request")
    op.drop_index("ix_doctor_review_request_doctor_status", table_name="doctor_review_request")
    op.drop_index("ix_doctor_review_request_patient_status", table_name="doctor_review_request")
    op.drop_index("uq_doctor_review_request_idempotency", table_name="doctor_review_request")
    op.drop_table("doctor_review_request")
