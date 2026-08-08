"""Phase 5: bang prescription + dose_event - chi du de tool
tra_cuu_lich_uong_ca_nhan/tra_cuu_don_thuoc_ca_nhan query duoc that (khong
phai FEAT-001-004 day du, xem ghi chu trong src/db/models.py).

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prescription",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("doctor_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prescription_patient_id", "prescription", ["patient_id"])

    op.create_table(
        "dose_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("prescription_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expected_items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dose_event_prescription_id", "dose_event", ["prescription_id"])
    op.create_index("ix_dose_event_patient_id", "dose_event", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_dose_event_patient_id", table_name="dose_event")
    op.drop_index("ix_dose_event_prescription_id", table_name="dose_event")
    op.drop_table("dose_event")
    op.drop_index("ix_prescription_patient_id", table_name="prescription")
    op.drop_table("prescription")
