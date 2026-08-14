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

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-14

LUU Y ve revision chain: danh so ban dau la 0022/down_revision=0021, trung
voi 0022_hourly_conversation_summaries.py (cung down_revision=0021, merge
gan nhau vao main - cung tinh trang da xay ra o migration 0021, xem ghi chu
trong file do). Doi lai so hieu 0023, xuong revise "0022" de co 1 chuoi
tuyen tinh duy nhat 0021 -> 0022 -> 0023 -> 0024. Doi metadata thuan tuy
truoc khi deploy that, khong anh huong noi dung migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
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
