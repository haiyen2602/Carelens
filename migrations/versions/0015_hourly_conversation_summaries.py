"""Add independent hourly conversation summaries for Vong 4.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hourly_conversation_summaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("patient_id", "hour_bucket", name="uq_hourly_conversation_summaries_patient_hour"),
    )
    op.create_index("ix_hourly_conversation_summaries_patient_id", "hourly_conversation_summaries", ["patient_id"])
    op.create_index("ix_hourly_conversation_summaries_hour_bucket", "hourly_conversation_summaries", ["hour_bucket"])


def downgrade() -> None:
    op.drop_index("ix_hourly_conversation_summaries_hour_bucket", table_name="hourly_conversation_summaries")
    op.drop_index("ix_hourly_conversation_summaries_patient_id", table_name="hourly_conversation_summaries")
    op.drop_table("hourly_conversation_summaries")
