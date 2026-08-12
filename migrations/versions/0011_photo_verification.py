"""Bang photo_verification - luu tung lan gui anh xac nhan lieu thuoc (ADR-0011).

1 dong = 1 LAN gui anh, khong phai 1 lieu: ADR-0011 cho toi da 2 lan chup lai
(tong 3 lan), can giu ca 3 de sau nay do duoc ty le roi vao nhanh nguoi than
duyet - chi so ma ADR-0011 yeu cau theo doi.

BR-4.2: moi lan gui anh phai luu detected_count, expected_count, confidence.
BR-4.3: anh la du lieu y te, chi luu DUONG DAN o day, file de ngoai repo.

Xem ghi chu ve `ket_qua` (3 gia tri, khong phai boolean) trong
backend/db/models.py::PhotoVerification.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_verification",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dose_event_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("expected_by_form", sa.JSON(), nullable=False),
        sa.Column("detected_by_form", sa.JSON(), nullable=False),
        sa.Column("ket_qua", sa.String(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("ghi_chu", sa.Text(), nullable=True),
        sa.Column("thong_bao", sa.Text(), nullable=False),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_photo_verification_dose_event_id", "photo_verification", ["dose_event_id"])
    op.create_index("ix_photo_verification_patient_id", "photo_verification", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_photo_verification_patient_id", table_name="photo_verification")
    op.drop_index("ix_photo_verification_dose_event_id", table_name="photo_verification")
    op.drop_table("photo_verification")
