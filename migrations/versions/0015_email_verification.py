"""Add email verification columns to account table: is_email_verified, email_verification_token, email_verification_expires_at.

Revision ID: 0015
Revises: 0014b
Create Date: 2026-08-13

LUU Y ve revision chain (2026-08-13, luc merge PR#23 va PR#24 vao main gan
nhau): file nay ban dau down_revision="0014", nhung "0014" khong con la head
duy nhat - 0014b_drug_catalog.py (doi ten tu 0014_drug_catalog.py, xem ghi
chu trong file do) cung down_revision="0014". Sua lai day xuong revise
"0014b" de co 1 chuoi tuyen tinh duy nhat 0014 -> 0014b -> 0015, khong bo
sot drug_catalog. Doi metadata thuan tuy - khong anh huong migration DA
CHAY (production da ap dung file nay tu truoc voi noi dung khong doi).
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account", sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("account", sa.Column("email_verification_token", sa.String(), nullable=True))
    op.add_column("account", sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_account_email_verification_token", "account", ["email_verification_token"])


def downgrade() -> None:
    op.drop_index("ix_account_email_verification_token", table_name="account")
    op.drop_column("account", "email_verification_expires_at")
    op.drop_column("account", "email_verification_token")
    op.drop_column("account", "is_email_verified")
