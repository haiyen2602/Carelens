"""Them cot `patient.watch` (bool, mac dinh false) - bac si tu chon "theo
doi" mot benh nhan cu the tren dashboard bao cao (backend/api/reporting_routes.py).
Xem ghi chu day du trong backend/db/models.py::Patient.

LUU Y ve revision chain: repo tung co 2 file cung mang revision "0014"
(0014_chat_messages.py va 0014_drug_catalog.py, ca 2 cung down_revision=
"0013" - trung lap tu truoc, KHONG phai do migration nay gay ra). Da sua:
0014_drug_catalog.py doi thanh revision "0014b", down_revision="0014", xep
sau 0014_chat_messages.py - chuoi lai tuyen tinh 0013->0014->0014b->0015.

Revision ID: 0015
Revises: 0014b
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("watch", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("patient", "watch")
