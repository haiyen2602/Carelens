"""Them cot `status` (pending|accepted) vao caregiver_link - cho phep 2
benh nhan tu dong y voi nhau thay vi chi admin duoc tao lien ket (mo rong
sau khi trien khai, xem backend/api/caregiver_routes.py).

Lien ket admin tao (POST /caregiver-links, require_role admin) van la
"accepted" ngay - admin da xac nhan thay, khong can duyet lai. Lien ket tu
loi moi tu benh nhan (POST /caregiver-links/invites) bat dau "pending" cho
toi khi nguoi duoc theo doi tu chap nhan.

server_default='accepted' de cac dong da co san (tao qua admin truoc khi
co cot nay) tu dong coi la da duyet, khong bi an di khoi man hinh dang
theo doi.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "caregiver_link",
        sa.Column("status", sa.String(), nullable=False, server_default="accepted"),
    )


def downgrade() -> None:
    op.drop_column("caregiver_link", "status")
