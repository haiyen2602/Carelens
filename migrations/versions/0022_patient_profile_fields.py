"""Add phone, address, date_of_birth, profile_completed to patient - trang
onboarding "Thong tin ca nhan" ma benh nhan tu dien ngay sau khi dang ky
(frontend/src/app/onboarding/profile/page.tsx).

Khong xoa/thay `year_of_birth` (migration 0009) - nhieu noi (PatientSummary,
bao cao) da doc cot nay. `date_of_birth` la nguon nhap moi, chinh xac hon
(ngay thay vi chi nam); khi benh nhan luu profile, dong bo year_of_birth =
date_of_birth.year de code cu khong phai sua (xem backend/api/patient_routes.py).

`profile_completed` (default False) - co de frontend biet co can bat buoc
redirect sang trang onboarding hay khong, KHONG suy tu viec cac cot khac co
NULL hay khong (benh nhan co the co y de trong 1 truong nao do sau nay).

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("phone", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("patient", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column(
        "patient",
        sa.Column("profile_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("patient", "profile_completed")
    op.drop_column("patient", "date_of_birth")
    op.drop_column("patient", "address")
    op.drop_column("patient", "phone")
