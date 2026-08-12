"""TASK-010: bang account - auth-api that (api-contracts.md muc 1), thay
rao tam X-Internal-Secret (backend/api/security.py). 1 bang chung cho ca 4
role (doctor|patient|caregiver|admin), khong tach rieng theo role (quyet
dinh 2026-08-12 voi PM, xem tasks/TASK-010-auth-api.md). Danh so lai
0009->0012 (2026-08-13) - main da dung 0009/0010/0011 cho patient/
prescription_fields/photo_verification luc branch nay dang lam viec rieng.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=True),
        sa.Column("doctor_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_email", "account", ["email"], unique=True)
    op.create_index("ix_account_patient_id", "account", ["patient_id"])
    op.create_index("ix_account_doctor_id", "account", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_account_doctor_id", table_name="account")
    op.drop_index("ix_account_patient_id", table_name="account")
    op.drop_index("ix_account_email", table_name="account")
    op.drop_table("account")
