"""Vong 2: bang pending_drug_confirmation - luu trang thai "dang cho benh
nhan xac nhan danh tinh thuoc" GIUA 2 lan goi HTTP (chatbot-rag-design.md
muc 11.3). patient_id la PRIMARY KEY (1 benh nhan toi da 1 pending
confirmation tai 1 thoi diem).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_drug_confirmation",
        sa.Column("patient_id", sa.String(), primary_key=True),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pending_drug_confirmation")