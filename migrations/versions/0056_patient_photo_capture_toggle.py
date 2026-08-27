"""Them cot photo_capture_enabled vao patient (THEM 2026-08-27).

Muc dich: man hinh Cai dat cho benh nhan tu bat/tat yeu cau chup anh khi xac
nhan uong thuoc. Khi tat, patient/page.tsx (frontend) coi MOI lieu la "khong
can anh" (giong nhu lieu qua gio/da hoan hien nay) - nut chinh luon la
"Toi da uong" / "Chua uong" thay vi mo camera. Bam "Toi da uong" van chuyen
dose_event sang AWAITING_CAREGIVER (tai su dung dung luong nguoi than duyet
da co san, xem backend/services/photo_verification/verifier.py va
frontend/src/app/patient/family/[id]/page.tsx) - KHONG tu dong chot TAKEN,
van can nguoi than xac nhan that.

Cot NOT NULL voi server_default=true: gia tri mac dinh phai KHOP hanh vi
hien tai (chup anh) de cac ban ghi patient cu khong bi doi hanh vi ngoai y
muon ngay sau khi chay migration.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-27

"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "patient",
        sa.Column(
            "photo_capture_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("patient", "photo_capture_enabled")
