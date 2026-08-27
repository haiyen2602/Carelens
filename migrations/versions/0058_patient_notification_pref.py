"""Tuy chon thong bao cua benh nhan - tang 1 "loai", tang 2 "kenh" (THEM 2026-08-27).

TAI SAO CAN TACH 2 TANG: truoc do man hinh Cai dat co 3 cong tac gia
("Nhac uong thuoc", "Canh bao khan cap", "Tong ket tuan") deu chi la useState
o client, khong luu gi. Khi them Telegram lam kenh thu hai, cach bay 3 cong
tac do canh 1 cong tac THAT tro nen nguy hiem: benh nhan gat "Nhac uong
thuoc" sang tat, tuong da tat, nhung van nhan tin Telegram.

`dose_reminder_enabled` la tang 1 (CO nhac hay khong), `web_push_enabled` la
tang 2 (nhac qua duong nao). Kenh Telegram KHONG nam o day ma o
telegram_link.enabled (migration 0057) - kenh do chi co y nghia khi ton tai
lien ket, luu chung voi lien ket la dung cho hon.

Bang 1-dong-moi-benh-nhan, va CO Y khong tao san dong nao: khong co dong =
dung mac dinh (bat het). Chi ghi khi benh nhan that su doi tuy chon.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_notification_pref",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("dose_reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("web_push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # 1 benh nhan chi co 1 dong tuy chon - dat UNIQUE de 2 request cung
        # luc khong tao ra 2 dong roi doc phai dong cu.
        sa.UniqueConstraint("patient_id", name="uq_patient_notification_pref_patient_id"),
    )


def downgrade() -> None:
    op.drop_table("patient_notification_pref")
