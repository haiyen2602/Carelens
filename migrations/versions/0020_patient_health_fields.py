"""Add gender, height_cm, weight_kg to patient - tab "Tinh trang suc khoe"
o trang Quan ly benh nhan (frontend/src/app/doctor/patients/page.tsx).

Khong gop vao `note` (text tu do, dang dung nhu chan doan/benh nen) vi day
la du lieu co cau truc (so, don vi ro rang) can hien thi/nhap rieng, khac
voi mo ta tu do.

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
    op.add_column("patient", sa.Column("gender", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("patient", sa.Column("weight_kg", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("patient", "weight_kg")
    op.drop_column("patient", "height_cm")
    op.drop_column("patient", "gender")
