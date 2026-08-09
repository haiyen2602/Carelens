"""Set drug_chunks.ten_thuoc NOT NULL - chay sau khi backfill (scripts/
backfill_ten_thuoc.py) da xac nhan 0 dong NULL con lai.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("drug_chunks", "ten_thuoc", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.alter_column("drug_chunks", "ten_thuoc", existing_type=sa.String(), nullable=True)
