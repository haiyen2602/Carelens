"""Bang patient - ho so benh nhan (KHONG phai tai khoan dang nhap).

Truoc migration nay `patient_id` chi la mot chuoi tran trong prescription/
dose_event/escalation, khong co gi rang buoc: go sai "demo-patient-1" thay vi
"demo-patient-01" thi he thong van nhan, don thuoc treo lo lung khong thuoc ve
ai, va KHONG co loi nao bao ra.

Xem ghi chu day du (vi sao khong co cot mat khau, vi sao chua dat khoa ngoai)
trong backend/db/models.py::Patient.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("year_of_birth", sa.Integer(), nullable=True),
        sa.Column("doctor_id", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patient_doctor_id", "patient", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_doctor_id", table_name="patient")
    op.drop_table("patient")
