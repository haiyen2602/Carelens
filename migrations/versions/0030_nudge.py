"""Bang nudge - 1 loi nhac nhe nguoi than gui cho benh nhan dang theo doi
(THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::Nudge (vi
sao khong dat FK, co che seen_at "pop khoi hang doi").

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nudge",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("caregiver_account_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_nudge_caregiver_account_id", "nudge", ["caregiver_account_id"])
    op.create_index("ix_nudge_patient_id", "nudge", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_nudge_patient_id", table_name="nudge")
    op.drop_index("ix_nudge_caregiver_account_id", table_name="nudge")
    op.drop_table("nudge")
