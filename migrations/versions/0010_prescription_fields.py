"""3 cot con thieu cua prescription so voi PrescriptionDTO (api-contracts.md §2).

  note        - o "Luu y" tren form bac si ke don, hien khong co cho luu.
  approved_by - BR-1.5: moi chuyen trang thai phai ghi actor + thoi diem.
  approved_at   Khong co 2 cot nay thi khong tra loi duoc "ai duyet phac do
                nay, luc nao" - cau hoi bat buoc phai tra loi duoc trong ho so
                y te.

Ca 3 deu nullable nen du lieu prescription san co khong hong.

`status` KHONG can migration: no dang la sa.String() thuong (danh sach gia tri
chi nam trong comment cua model, khong phai enum cua DB), nen them "rejected"
chi la them mot hang so trong code.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prescription", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("prescription", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("prescription", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("prescription", "approved_at")
    op.drop_column("prescription", "approved_by")
    op.drop_column("prescription", "note")
