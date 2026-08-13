"""Bang drug - danh muc thuoc co cau truc (dang bao che, duong dung, ham luong).

KHAC drug_chunks: bang do la san pham RAG (4 chunk/thuoc, co embedding) dung de
TRA LOI CAU HOI. Bang nay la DANH MUC dung de TRA CUU khi bac si ke don, va la
nguon duy nhat cho `dang_thuoc` - truong quyet dinh mot lieu thuoc co xac minh
duoc bang anh hay khong (backend/services/photo_verification/dosage_form.py).

Vi sao khong them cot vao drug_chunks: bang do lap 4 dong moi thuoc, va chi
chua thuoc DA EMBED (226/3562). Danh muc phai du 3562 thuoc thi bac si moi ke
duoc don, khong the phu thuoc vao tien do embed.

GIN trigram index tren cot da bo dau - cung quy uoc voi drug_chunks (migration
0001): bat buoc unaccent truoc khi index va truoc khi query, neu khong thi go
"vien nen" se khong tim ra "viên nén".

Danh so lai 0012->0015 (2026-08-13): trung revision voi 0012_account.py (2
migration doc lap cung danh so 0012). Xep sau 0014_chat_messages.py de co
mot chuoi tuyen tinh duy nhat, khong doi thu tu that cua 2 thay doi (bang nay
khong phu thuoc gi vao bang account).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drug",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("ten_thuoc", sa.String(), nullable=False),
        sa.Column("ten_thuoc_unaccent", sa.Text(), nullable=False),
        sa.Column("dang_thuoc", sa.String(), nullable=False),
        sa.Column("duong_dung", sa.String(), nullable=False),
        sa.Column("ham_luong", sa.String(), nullable=True),
        sa.Column("tong_so_luong", sa.String(), nullable=True),
        sa.Column("danh_muc", sa.String(), nullable=True),
        sa.Column("muc_nghiem_trong", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drug_ten_thuoc", "drug", ["ten_thuoc"])
    # Tim theo ten go gan dung: similarity() tren cot da bo dau.
    op.execute(
        "CREATE INDEX ix_drug_ten_thuoc_unaccent_trgm ON drug "
        "USING gin (ten_thuoc_unaccent gin_trgm_ops)"
    )
    # Loc theo dang bao che khi can thong ke (vd bao nhieu thuoc dang tiem).
    op.create_index("ix_drug_dang_thuoc", "drug", ["dang_thuoc"])


def downgrade() -> None:
    op.drop_index("ix_drug_dang_thuoc", table_name="drug")
    op.execute("DROP INDEX IF EXISTS ix_drug_ten_thuoc_unaccent_trgm")
    op.drop_index("ix_drug_ten_thuoc", table_name="drug")
    op.drop_table("drug")
