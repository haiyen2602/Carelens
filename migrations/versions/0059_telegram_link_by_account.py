"""Doi khoa telegram_link tu patient_id sang account_id (SUA 2026-08-28).

TAI SAO PHAI DOI: ban dau (migration 0056) chi co benh nhan nhan tin, nen
khoa theo patient_id la du. Gio NGUOI THAN cung phai nhan duoc canh bao khi
benh nhan bo lieu - ma nguoi than khong co patient_id, ho la mot Account
role=caregiver noi voi benh nhan qua bang caregiver_link.

Khoa theo account_id giai quyet ca hai: "1 tai khoan = 1 Telegram", khong
phan biet tai khoan do la benh nhan hay nguoi than. Ai gui cho ai la viec cua
tang service (backend/services/telegram.py), khong phai cua bang nay.

Cung xu ly luon truong hop nguoi VUA LA benh nhan VUA LA nguoi than cua vo/
chong: truoc day se can 2 dong nhung chat_id UNIQUE chan mat, gio chi 1 dong
duy nhat va nhan ca hai loai tin.

An toan khi chay: tinh nang chua len production, chi co du lieu thu o may
dev. Van backfill dang hoang thay vi xoa trang - ai da ghep thu o local
khong bi mat lien ket.

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telegram_link", sa.Column("account_id", sa.String(), nullable=True))

    # Backfill: patient_id -> account role=patient tuong ung. Dong nao khong
    # tim duoc tai khoan (du lieu thu voi patient_id bia) se bi xoa ben duoi -
    # giu lai cung vo dung vi khong biet gui cho ai.
    op.execute(
        """
        UPDATE telegram_link tl
           SET account_id = a.id
          FROM account a
         WHERE a.patient_id = tl.patient_id
           AND a.role = 'patient'
        """
    )
    op.execute("DELETE FROM telegram_link WHERE account_id IS NULL")

    op.alter_column("telegram_link", "account_id", nullable=False)
    op.create_unique_constraint("uq_telegram_link_account_id", "telegram_link", ["account_id"])

    op.drop_index("ix_telegram_link_patient_id", table_name="telegram_link")
    op.drop_column("telegram_link", "patient_id")

    # Token ghep cung doi theo: token sinh ra cho 1 TAI KHOAN dang dang nhap,
    # khong phai cho 1 ho so benh nhan.
    op.add_column("telegram_link_token", sa.Column("account_id", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE telegram_link_token t
           SET account_id = a.id
          FROM account a
         WHERE a.patient_id = t.patient_id
           AND a.role = 'patient'
        """
    )
    # Token la thu song 10 phut - dong nao khong map duoc thi xoa, khong ai
    # mat gi (bam "Kết nối" lai la co token moi).
    op.execute("DELETE FROM telegram_link_token WHERE account_id IS NULL")
    op.alter_column("telegram_link_token", "account_id", nullable=False)
    op.create_index("ix_telegram_link_token_account_id", "telegram_link_token", ["account_id"])
    op.drop_index("ix_telegram_link_token_patient_id", table_name="telegram_link_token")
    op.drop_column("telegram_link_token", "patient_id")


def downgrade() -> None:
    op.add_column("telegram_link", sa.Column("patient_id", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE telegram_link tl
           SET patient_id = a.patient_id
          FROM account a
         WHERE a.id = tl.account_id
        """
    )
    op.execute("DELETE FROM telegram_link WHERE patient_id IS NULL")
    op.alter_column("telegram_link", "patient_id", nullable=False)
    op.create_index("ix_telegram_link_patient_id", "telegram_link", ["patient_id"])
    op.drop_constraint("uq_telegram_link_account_id", "telegram_link", type_="unique")
    op.drop_column("telegram_link", "account_id")

    op.add_column("telegram_link_token", sa.Column("patient_id", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE telegram_link_token t
           SET patient_id = a.patient_id
          FROM account a
         WHERE a.id = t.account_id
        """
    )
    op.execute("DELETE FROM telegram_link_token WHERE patient_id IS NULL")
    op.alter_column("telegram_link_token", "patient_id", nullable=False)
    op.create_index("ix_telegram_link_token_patient_id", "telegram_link_token", ["patient_id"])
    op.drop_index("ix_telegram_link_token_account_id", table_name="telegram_link_token")
    op.drop_column("telegram_link_token", "account_id")
