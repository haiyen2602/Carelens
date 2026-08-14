"""Doi "Theo doi" tu 1 co chung tren patient thanh quan he rieng theo tung
bac si (nhieu bac si co the theo doi doc lap 1 benh nhan) - quyet dinh PM
2026-08-14.

`patient.watch` (migration 0015) la 1 co BOOLEAN DUNG CHUNG - khong biet
CHINH XAC bac si nao da bam "Theo doi", nen khong dung lam dieu kien loc
"Hop canh bao" theo tung bac si duoc (2 bac si cung thay 1 benh nhan, 1
nguoi bam thi ca 2 deu bi anh huong chung 1 co). Thay bang bang lien ket
`doctor_watch` (doctor_id, patient_id) - cung mau voi `caregiver_link`
(migration 0016). Dung lam dich loc GET /escalations (backend/api/
reporting_routes.py) - bac si CHI thay canh bao cua benh nhan minh dang
theo doi, khong phai toan bo benh nhan trong he thong.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("patient", "watch")

    op.create_table(
        "doctor_watch",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("doctor_id", sa.String(), nullable=False, index=True),
        sa.Column("patient_id", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("doctor_id", "patient_id", name="uq_doctor_watch_doctor_patient"),
    )


def downgrade() -> None:
    op.drop_table("doctor_watch")
    op.add_column("patient", sa.Column("watch", sa.Boolean(), nullable=False, server_default=sa.false()))
