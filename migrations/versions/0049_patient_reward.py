"""Bang patient_reward_account + patient_reward_event - he thong diem thuong
va Rank tron doi cho benh nhan (THEM 2026-08-25).

Xem ghi chu day du trong backend/db/models.py::PatientRewardAccount /
PatientRewardEvent (vi sao tach LP/SP lam 2 cot, vi sao khoa duy nhat co
occurred_on NULL cho REDEEM).

Danh muc qua tang KHONG co bang rieng - de lam hang so trong
backend/services/reward_catalog.py (10 mon, tinh, gan voi thoa thuan
Vinmec). `patient_reward_event.item_id` tro toi slug trong file do.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-25

"""

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_reward_account",
        sa.Column("patient_id", sa.String(), primary_key=True),
        sa.Column("lifetime_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spendable_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "patient_reward_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("points_delta", sa.Integer(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patient_reward_event_patient_id", "patient_reward_event", ["patient_id"])
    op.create_index(
        "ix_patient_reward_event_patient_created",
        "patient_reward_event",
        ["patient_id", "created_at"],
    )
    op.create_index(
        "ix_patient_reward_event_patient_item",
        "patient_reward_event",
        ["patient_id", "item_id"],
    )
    # "1 lan/ngay" thanh rang buoc o tang DB, khong chi la if/else o service.
    # REDEEM co occurred_on = NULL nen khong bao gio dung constraint nay
    # (Postgres coi moi NULL la khac nhau) - dung nhu thiet ke.
    op.create_unique_constraint(
        "uq_patient_reward_event_daily",
        "patient_reward_event",
        ["patient_id", "event_type", "occurred_on"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_patient_reward_event_daily", "patient_reward_event", type_="unique"
    )
    op.drop_index("ix_patient_reward_event_patient_item", table_name="patient_reward_event")
    op.drop_index("ix_patient_reward_event_patient_created", table_name="patient_reward_event")
    op.drop_index("ix_patient_reward_event_patient_id", table_name="patient_reward_event")
    op.drop_table("patient_reward_event")
    op.drop_table("patient_reward_account")
