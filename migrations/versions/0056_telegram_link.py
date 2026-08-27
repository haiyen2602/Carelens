"""Kenh nhac gio uong thuoc qua Telegram bot (THEM 2026-08-27).

Vi sao can 2 bang chu khong phai 1: `telegram_link` la ket qua CUOI (benh
nhan nao <-> chat_id nao), con `telegram_link_token` la ma dung 1 lan de
GHEP hai thu do lai voi nhau mot cach an toan.

Khong the bo bang token di roi cho benh nhan tu nhap chat_id: Bot API cua
Telegram KHONG cho tra chat_id tu so dien thoai/email (chong spam, xem
backend/services/telegram.py), nen chat_id chi xuat hien khi chinh benh nhan
bam /start voi bot. Token la thu duy nhat noi duoc "nguoi vua bam /start" voi
"benh nhan dang dang nhap tren web".

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_link",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        # chat_id la BigInteger, KHONG phai Integer: Telegram da cap id vuot
        # 2^31 tu lau (tai khoan moi thuong ~7-8 chu so nhung nhom/kenh am va
        # co the toi 52 bit) - dung Integer se tran khi app chay that.
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # 1 tai khoan Telegram chi gan duoc 1 benh nhan. Dat UNIQUE o chat_id
        # (khong phai patient_id) vi benh nhan co the doi may/doi tai khoan
        # Telegram, luc do nen ton tai them 1 dong moi thay vi chan lai.
        sa.UniqueConstraint("chat_id", name="uq_telegram_link_chat_id"),
    )
    op.create_index("ix_telegram_link_patient_id", "telegram_link", ["patient_id"])

    op.create_table(
        "telegram_link_token",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_telegram_link_token_token"),
    )
    op.create_index("ix_telegram_link_token_patient_id", "telegram_link_token", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_link_token_patient_id", table_name="telegram_link_token")
    op.drop_table("telegram_link_token")
    op.drop_index("ix_telegram_link_patient_id", table_name="telegram_link")
    op.drop_table("telegram_link")
