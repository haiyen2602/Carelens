"""Phase 4: them cot ten_thuoc vao drug_chunks (thieu tu Phase 1 - phat hien
luc viet retrieval.py, DrugInfoDTO bat buoc co ten_thuoc theo api-contracts.md
§8, nhung Phase 1/3 chi luu ten_thuoc_unaccent de so khop, khong luu ban goc).

Them cot nullable truoc, BACKFILL BANG scripts/backfill_ten_thuoc.py (doc tu
data pharmacy/*.json, nguon that duy nhat), roi moi set NOT NULL o migration
0003 sau khi xac nhan backfill xong 100%.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drug_chunks", sa.Column("ten_thuoc", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("drug_chunks", "ten_thuoc")
