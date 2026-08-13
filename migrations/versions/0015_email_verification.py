"""Add email verification columns to account table: is_email_verified, email_verification_token, email_verification_expires_at.

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
    op.add_column("account", sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("account", sa.Column("email_verification_token", sa.String(), nullable=True))
    op.add_column("account", sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_account_email_verification_token", "account", ["email_verification_token"])


def downgrade() -> None:
    op.drop_index("ix_account_email_verification_token", table_name="account")
    op.drop_column("account", "email_verification_expires_at")
    op.drop_column("account", "email_verification_token")
    op.drop_column("account", "is_email_verified")
