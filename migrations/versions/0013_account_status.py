"""TASK-010 follow-up: account-api (admin quan ly tai khoan) - them cot
`status` (active|locked) vao bang account. Xem tasks/TASK-010-auth-api.md
va backend/api/account_routes.py. Danh so lai 0010->0013 (2026-08-13, cung
ly do voi 0012_account.py).

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account", sa.Column("status", sa.String(), nullable=False, server_default="active"))


def downgrade() -> None:
    op.drop_column("account", "status")
