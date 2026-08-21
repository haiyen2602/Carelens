"""Bang push_subscription + push_reminder_sent - Web Push cho nhac gio uong
thuoc (THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::
PushSubscription / PushReminderSent (vi sao endpoint UNIQUE, vi sao khoa
duy nhat cua push_reminder_sent la khung gio chu khong phai dose_event_id).

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_push_subscription_patient_id", "push_subscription", ["patient_id"])
    # UNIQUE tren endpoint = "1 thiet bi 1 dong": subscribe lai tu cung may
    # phai UPSERT, khong duoc de sinh 2 dong roi ban trung 2 lan.
    op.create_unique_constraint("uq_push_subscription_endpoint", "push_subscription", ["endpoint"])

    op.create_table(
        "push_reminder_sent",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("slot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moc", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_push_reminder_sent_slot", "push_reminder_sent", ["patient_id", "slot_at", "moc"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_push_reminder_sent_slot", "push_reminder_sent", type_="unique")
    op.drop_table("push_reminder_sent")
    op.drop_constraint("uq_push_subscription_endpoint", "push_subscription", type_="unique")
    op.drop_index("ix_push_subscription_patient_id", table_name="push_subscription")
    op.drop_table("push_subscription")
