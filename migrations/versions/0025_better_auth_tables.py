"""Login with Google (Better Auth) - 4 bang rieng cua Better Auth + cot
`auth_provider` tren `account`.

Better Auth (chay trong Next.js, frontend/src/lib/better-auth.ts) BAT BUOC co
schema rieng cua no: user/session/account/verification. Bang `account` cua du
an DA TON TAI voi hinh dang HOAN TOAN KHAC (role/patient_id/password_hash,
migration 0012) nen KHONG the dung chung ten - vi vay 4 bang o day mang tien
to `ba_` va duoc khai bao lai qua `modelName` trong cau hinh Better Auth.

Better Auth CHI la moi gioi OAuth: sau khi Google xac thuc xong, Route Handler
frontend/src/app/api/auth/google-bridge/route.ts doi danh tinh do sang JWT that
cua backend (POST /api/v1/auth/oauth/google). Nguon su that ve danh tinh VAN LA
bang `account` + JWT - moi route backend khong doi mot dong nao.

`account.auth_provider` ("password" | "google"): de biet tai khoan nao sinh ra
tu Google. BAT BUOC ve mat bao mat, khong phai de trang tri: tai khoan tao qua
Google KHONG co mat khau nguoi dung nao ca, `password_hash` cua no chi la
bcrypt cua 1 chuoi ngau nhien khong ai biet (xem backend/api/auth_routes.py::
_oauth_upsert_account). Thieu cot nay thi UI/admin khong the phan biet "chua
dat mat khau" voi "co mat khau", va luong doi mat khau se hoi "mat khau hien
tai" cua mot thu khong ton tai.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("auth_provider", sa.String(), nullable=False, server_default="password"),
    )

    # 4 bang duoi day do BETTER AUTH so huu (frontend), backend KHONG doc/ghi.
    # Ten cot giu dung camelCase cua Better Auth (userId, expiresAt...) - day
    # la ten no sinh SQL truc tiep qua adapter Kysely, doi thanh snake_case se
    # lam no khong tim thay cot. Vi vay chung duoc quote trong DDL.
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


def downgrade() -> None:
    op.drop_table("ba_verification")
    op.drop_table("ba_account")
    op.drop_table("ba_session")
    op.drop_table("ba_user")
    op.drop_column("account", "auth_provider")
