"""Add password reset columns to account table: password_reset_token, password_reset_expires_at.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account", sa.Column("password_reset_token", sa.String(), nullable=True))
    op.add_column("account", sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_account_password_reset_token", "account", ["password_reset_token"])


def downgrade() -> None:
    op.drop_index("ix_account_password_reset_token", table_name="account")
    op.drop_column("account", "password_reset_expires_at")
    op.drop_column("account", "password_reset_token")
