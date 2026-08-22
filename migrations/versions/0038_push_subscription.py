"""Bang push_subscription + push_reminder_sent - Web Push cho nhac gio uong
thuoc (THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::
PushSubscription / PushReminderSent (vi sao endpoint UNIQUE, vi sao khoa
duy nhat cua push_reminder_sent la khung gio chu khong phai dose_event_id).

LUU Y ve revision chain (doi so 0031 -> 0032, 2026-08-22): ban dau file nay
la "0031" vi luc viet head la 0030. Trong luc do main merge
0031_remove_better_auth_and_add_supabase_uid.py CUNG lay so 0031 -> 2 file
trung revision id, alembic bao "Revision 0031 is present more than once" va
gay 2 head, hong ca chuoi migration. File Supabase DA len main (co the da
chay tren production) nen GIU nguyen so; file NAY doi thanh "0032", xep sau
no. Cung cach xu ly da lam o 0017_patient_watch.py/0018_caregiver_link.py.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
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
