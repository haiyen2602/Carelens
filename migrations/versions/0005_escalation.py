"""Phase 6: bang escalation - khop EscalationDTO (api-contracts.md §6/§8),
noi DUY NHAT ca 2 duong kich hoat HIGH (safety_layer redflag va
SEVERITY -> LEVEL = "Nguy hiểm") ghi vao qua escalate_fn dung chung
(backend/services/escalation.py).

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "escalation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("dose_event_id", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("raw_utterance", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("notified", sa.JSON(), nullable=False),
    )
    op.create_index("ix_escalation_patient_id", "escalation", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_escalation_patient_id", table_name="escalation")
    op.drop_table("escalation")