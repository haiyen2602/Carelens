"""Add gender, height_cm, weight_kg to patient - tab "Tinh trang suc khoe"
o trang Quan ly benh nhan (frontend/src/app/doctor/patients/page.tsx).

Khong gop vao `note` (text tu do, dang dung nhu chan doan/benh nen) vi day
la du lieu co cau truc (so, don vi ro rang) can hien thi/nhap rieng, khac
voi mo ta tu do.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-13

LUU Y ve revision chain (2026-08-13, luc merge PR#33 va PR#32 vao main gan
nhau): file nay ban dau danh so 0020/down_revision=0019, nhung trung voi
0020_caregiver_link_status.py (cung down_revision=0019, merge cung luc) -
tao 2 head re nhanh tu 0019. Doi lai so hieu 0021, xuong revise "0020" de
co 1 chuoi tuyen tinh duy nhat 0019 -> 0020 -> 0021. Doi metadata thuan tuy
truoc khi deploy that (railway.json preDeployCommand chay `alembic upgrade
head` - se bao loi "multiple heads" neu khong sua) - khong anh huong noi
dung migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("gender", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("patient", sa.Column("weight_kg", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("patient", "weight_kg")
    op.drop_column("patient", "height_cm")
    op.drop_column("patient", "gender")
