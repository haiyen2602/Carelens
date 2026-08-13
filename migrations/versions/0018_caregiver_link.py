"""Bang caregiver_link - lien ket bac si<->benh nhan<->nguoi than THAT
(specs/user-roles.md: 1 benh nhan co 0..n nguoi than, 1 nguoi than co the
gan voi nhieu benh nhan, CHI admin duoc quan ly lien ket nay). Xem ghi chu
day du trong backend/db/models.py::CaregiverLink (vi sao khong dat FK,
khac gi voi Account.patient_id da co tu TASK-010).

LUU Y ve revision chain (doi so 0016 -> 0018, 2026-08-13): xem ghi chu day
du trong 0017_patient_watch.py - trung so voi 0016_password_reset.py (PR
#23) luc merge gan nhau vao main. File password_reset DA CHAY tren
production nen giu nguyen so, file NAY doi thanh "0018", xep sau
0017_patient_watch.py.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "caregiver_link",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("caregiver_account_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_caregiver_link_caregiver_account_id", "caregiver_link", ["caregiver_account_id"])
    op.create_index("ix_caregiver_link_patient_id", "caregiver_link", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_caregiver_link_patient_id", table_name="caregiver_link")
    op.drop_index("ix_caregiver_link_caregiver_account_id", table_name="caregiver_link")
    op.drop_table("caregiver_link")
