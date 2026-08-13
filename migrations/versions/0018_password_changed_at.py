"""Add password_changed_at to account - thu hoi phien cu khi doi/dat lai mat khau.

Cot nay la MOC THOI GIAN de so voi claim `iat` cua JWT: moi token phat TRUOC
moc nay bi coi la het hieu luc (xem backend/services/auth.py::
token_revoked_by_password_change). NULL = tai khoan chua tung doi mat khau ->
khong thu hoi gi (tuong thich voi tai khoan da ton tai truoc migration nay).

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("account", "password_changed_at")
