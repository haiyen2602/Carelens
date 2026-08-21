"""Xoa cac bang Better Auth (ba_*) va them cot supabase_uid cho account.

Theo ADR-0013 (2026-08-21): Thay the Better Auth bang Supabase Auth.
4 bang ba_* duoc drop de don dep DB.
Cot `account.supabase_uid` duoc them de anh xa dinh danh Supabase (neu co).

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Them cot supabase_uid vao bang account (optional, unique)
    op.add_column(
        "account",
        sa.Column("supabase_uid", sa.String(), nullable=True),
    )
    op.create_index("ix_account_supabase_uid", "account", ["supabase_uid"], unique=True)

    # Drop 4 bang Better Auth neu ton tai (theo thu tu rang buoc khoa ngoai)
    # Dung check existence de an toan
    conn = op.get_bind()
    tables = [
        "ba_verification",
        "ba_account",
        "ba_session",
        "ba_user",
    ]
    for tbl in tables:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))


def downgrade() -> None:
    op.drop_index("ix_account_supabase_uid", table_name="account")
    op.drop_column("account", "supabase_uid")

    # Recreate 4 bang Better Auth neu can rollback
    op.create_table(
        "ba_user",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("emailVerified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ba_session",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("userId", sa.String(), sa.ForeignKey("ba_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ipAddress", sa.String(), nullable=True),
        sa.Column("userAgent", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ba_account",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("userId", sa.String(), sa.ForeignKey("ba_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accountId", sa.String(), nullable=False),
        sa.Column("providerId", sa.String(), nullable=False),
        sa.Column("accessToken", sa.String(), nullable=True),
        sa.Column("refreshToken", sa.String(), nullable=True),
        sa.Column("accessTokenExpiresAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshTokenExpiresAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("idToken", sa.String(), nullable=True),
        sa.Column("password", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("providerId", "accountId", name="uq_ba_account_provider_account"),
    )

    op.create_table(
        "ba_verification",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("identifier", sa.String(), nullable=False, index=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False),
    )
