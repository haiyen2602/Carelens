"""Bang push_subscription + push_reminder_sent - Web Push cho nhac gio uong
thuoc (THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::
PushSubscription / PushReminderSent (vi sao endpoint UNIQUE, vi sao khoa
duy nhat cua push_reminder_sent la khung gio chu khong phai dose_event_id).

LUU Y ve revision chain (doi so 0031 -> 0032 -> 0038, 2026-08-22): ban dau
file nay la "0031" vi luc viet head la 0030. Trong luc do main merge
0031_remove_better_auth_and_add_supabase_uid.py CUNG lay so 0031 -> 2 file
trung revision id, alembic bao "Revision 0031 is present more than once" va
gay 2 head, hong ca chuoi migration. Doi thanh "0032" (xep sau 0031) de vá lan
1. Sau do main lai merge THEM 0032_rag_corpus_recovery.py (cung tu "0032" ->
lap lai dung y het loi cu). Lan nay doi thanng "0038", xep sau CA chuoi
0032(rag)..0037(system_audit_logs) cua main - khong doi lai so cua main vi
chuoi do da co nhieu migration khac xay tren no (0033..0037), doi ca chuoi se
dung cham nhieu file hon la doi 1 file nay. Cung cach xu ly da lam o
0017_patient_watch.py/0018_caregiver_link.py.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
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
