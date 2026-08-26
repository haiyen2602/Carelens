"""Them cot points_awarded vao photo_verification (THEM 2026-08-26).

Muc dich UX: benh nhan chup anh xac nhan lieu thuoc, anh khop -> ngay lap
tuc thay "+N diem" tren man hinh ket qua, khong phai tu mo trang Diem thuong
de biet minh vua duoc thuong bao nhieu. Xem backend/services/photo_verification
/verifier.py (noi ghi gia tri) va backend/api/photo_routes.py::_to_out (noi
tra ve qua API).

Cot NULLABLE, khong co server_default: NULL = "khong ap dung" (lech/
khong_xac_minh_duoc/loi_he_thong/do_tin_cay_thap/AWAITING_CAREGIVER), phan
biet voi 0 = "co xet nhung khong duoc gi" (vd goi lai cung ngay, da cong du
tran). Xem ghi chu tren cot trong backend/db/models.py::PhotoVerification.

Rieng, khong gop vao migration 0050 (chia diem theo tung lieu): 0048 sua
bang patient_reward_event, con day la bang photo_verification - hai thay
doi doc lap, tach rieng de mot ben co the downgrade ma khong keo ben kia.

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photo_verification",
        sa.Column("points_awarded", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photo_verification", "points_awarded")
