"""Bang drug_request - duong thoat cho FB-14 (THEM 2026-08-21).

Tu 2026-08-20 danh muc thuoc la allowlist dong (services/prescription/
service.py::_chuan_hoa_item tu choi item khong co `drug_id`). Bang nay la
duong de bac si xin bo sung thuoc ngoai danh muc, admin duyet moi ke duoc.

Xem ghi chu day du trong backend/db/models.py::DrugRequest (vi sao khong ghi
thang vao bang `drug`, vi sao `dang_thuoc` NOT NULL, quy uoc `req-` cua
`approved_drug_id`).

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-21

"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug_request",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("requested_by_doctor_id", sa.String(), nullable=False),
        sa.Column("ten_thuoc", sa.String(), nullable=False),
        sa.Column("dang_thuoc", sa.String(), nullable=False),
        sa.Column("duong_dung", sa.String(), nullable=False),
        sa.Column("ham_luong", sa.String(), nullable=True),
        sa.Column("tong_so_luong", sa.String(), nullable=True),
        sa.Column("ly_do", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by_account_id", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_drug_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drug_request_requested_by_doctor_id", "drug_request", ["requested_by_doctor_id"])
    op.create_index("ix_drug_request_status", "drug_request", ["status"])
    # UNIQUE chu khong phai index thuong: `approved_drug_id` duoc dung lam
    # `drug_id` trong don thuoc, trung id la hai don tro ve hai thuoc khac nhau.
    op.create_unique_constraint("uq_drug_request_approved_drug_id", "drug_request", ["approved_drug_id"])


def downgrade() -> None:
    op.drop_constraint("uq_drug_request_approved_drug_id", "drug_request", type_="unique")
    op.drop_index("ix_drug_request_status", table_name="drug_request")
    op.drop_index("ix_drug_request_requested_by_doctor_id", table_name="drug_request")
    op.drop_table("drug_request")
