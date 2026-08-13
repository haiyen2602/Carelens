"""Them cot `patient.watch` (bool, mac dinh false) - bac si tu chon "theo
doi" mot benh nhan cu the tren dashboard bao cao (backend/api/reporting_routes.py).
Xem ghi chu day du trong backend/db/models.py::Patient.

LUU Y ve revision chain (doi so 0015 -> 0017, 2026-08-13): luc PR them
migration nay (#24) va PR feat/authn-authz (#23, them 0015_email_verification.py
+ 0016_password_reset.py) merge gan nhau vao main, ca 2 PR cung tu danh so
"0015"/"0016" doc lap - trung lap. Email_verification/password_reset DA
CHAY that tren production (xac nhan 2026-08-13: cot is_email_verified,
password_reset_token... da co san trong bang account) truoc khi phat hien
trung lap, nen giu nguyen so cua 2 file do; doi file NAY (chua chay tren
production) tu "0015" -> "0017", xep SAU 0016_password_reset.py de co lai
1 chuoi tuyen tinh duy nhat: 0014b -> 0015 (email_verification) -> 0016
(password_reset) -> 0017 (file nay) -> 0018 (caregiver_link).

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("watch", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("patient", "watch")
