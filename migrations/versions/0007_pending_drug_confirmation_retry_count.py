"""Vong 2 review: pending_drug_confirmation can 1 cot retry_count - dem so
lan LIEN TIEP reply KHONG parse duoc thanh yes/no/so thu tu o CUNG 1 stage
(khac round-budget da co, dem theo so ung vien da thu). Khong co cot nay,
benh nhan go linh tinh lien tuc co the lam he thong hoi lai VO HAN (round-
budget khong bi tieu ton boi reply khong parse duoc - phat hien qua review
2026-08-09, xem chatbot-rag-design.md muc 11.3).

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pending_drug_confirmation",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pending_drug_confirmation", "retry_count")