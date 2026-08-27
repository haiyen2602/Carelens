"""Add doctor-review takeover lifecycle columns and the doctor/patient
message thread for an active handoff.

BUILD-44: additive only. ``doctor_review_request`` gains ``activated_at``/
``resolved_at``/``resolved_by_doctor_id`` (all nullable) -- the existing
``ANSWERED``/``answered_at``/``answered_by_doctor_id``/``doctor_answer``
columns (BUILD-10) are untouched, kept as a separate, legacy "quick
answer" path distinct from the new take-over-and-converse lifecycle
(PENDING -> ASSIGNED -> ACTIVE -> RESOLVED, or -> CANCELLED). ``status``
itself stays a plain unconstrained ``String`` (matching every prior
migration's own convention for this table) -- no DB check constraint, so
adding the two new status values (``ACTIVE``/``RESOLVED``) needs no
migration of its own.

New table ``doctor_review_message``: the real-time patient/doctor/system
message thread for one handoff episode, scoped by ``handoff_id`` (not the
broader, always-on patient chat history -- see the BUILD-44 report's own
audit for why the existing ``chat_messages`` table was not reused: it is
only written by legacy ``chat_routes.py``, never Agent V2, and has no
handoff/conversation linkage at all).

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-26

Renumbered from the original 0053 (BUILD-44 branched from the same 0052
head as Track B's 0053_drug_image_embeddings.py, which merged to main
first) -- content/logic unchanged, only revision/down_revision updated to
chain after it. See the BUILD-44 report's own account of this.
"""

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("doctor_review_request", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("doctor_review_request", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("doctor_review_request", sa.Column("resolved_by_doctor_id", sa.String(), nullable=True))

    op.create_table(
        "doctor_review_message",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("handoff_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("sender_role", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sender_role IN ('PATIENT', 'DOCTOR', 'SYSTEM')", name="ck_doctor_review_message_sender_role"
        ),
        sa.ForeignKeyConstraint(["handoff_id"], ["doctor_review_request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_doctor_review_message_handoff_created", "doctor_review_message", ["handoff_id", "created_at"]
    )
    op.create_index("ix_doctor_review_message_patient_id", "doctor_review_message", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_doctor_review_message_patient_id", table_name="doctor_review_message")
    op.drop_index("ix_doctor_review_message_handoff_created", table_name="doctor_review_message")
    op.drop_table("doctor_review_message")
    op.drop_column("doctor_review_request", "resolved_by_doctor_id")
    op.drop_column("doctor_review_request", "resolved_at")
    op.drop_column("doctor_review_request", "activated_at")
