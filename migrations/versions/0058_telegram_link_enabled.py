"""Cho benh nhan TAM TAT nhac qua Telegram ma khong mat lien ket (THEM 2026-08-27).

Truoc cot nay, cach duy nhat de thoi nhan tin la xoa han lien ket (DELETE
/telegram/link) - muon nhan lai thi phai lam LAI toan bo luong ghep: vao web,
xin link moi, mo Telegram, bam Start. Voi benh nhan cao tuoi thi mot lan tat
di gan nhu la mat luon tinh nang.

`enabled` tach "co ket noi khong" khoi "co muon nhan khong" - hai cau hoi
khac nhau ma truoc do bi gop lam mot.

Default TRUE va NOT NULL: moi dong dang co deu la benh nhan da chu dong bam
Ket noi, y dinh cua ho ro rang la CO muon nhan.

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
    op.add_column(
        "telegram_link",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("telegram_link", "enabled")
