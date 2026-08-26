"""BUILD: Upgrade first existing admin to super_admin.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-26

"""

from alembic import op
import sqlalchemy as sa


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nang cap tai khoan admin dau tien (hoac tat ca admin tao truoc day) len super_admin
    # de dam bao he thong khong bi mat quyen super_admin khi them phan quyen
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE account
            SET role = 'super_admin'
            WHERE role = 'admin'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE account
            SET role = 'admin'
            WHERE role = 'super_admin'
            """
        )
    )
