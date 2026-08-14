"""Add independent hourly conversation summaries for Vong 4.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-13

LUU Y ve revision chain (2026-08-14, phan hoi review PR#37): file nay ban dau
danh so 0015/down_revision=0014, nhung trung voi 0015_email_verification.py
da co san tren main (cung nhanh doi tu 0014b, khac dong migration hoan toan -
xay dung song song, khong ai biet ve file kia luc code). Doi lai so hieu 0022,
down_revision "0021" (head that cua main tai thoi diem review, sau khi
fix/migration-revision-collision-0020 da merge) de co 1 chuoi tuyen tinh duy
nhat - dung cung mau da dung o 0021_patient_health_fields.py (doi 0020->0021
cho vu va cham PR#32/PR#33). Doi metadata thuan tuy, khong doi noi dung
migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
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
