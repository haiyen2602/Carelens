"""Bang push_subscription + push_reminder_sent - Web Push cho nhac gio uong
thuoc (THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::
PushSubscription / PushReminderSent (vi sao endpoint UNIQUE, vi sao khoa
duy nhat cua push_reminder_sent la khung gio chu khong phai dose_event_id).

LUU Y ve revision chain (doi so 0031 -> 0032 -> 0038 -> 0041, 2026-08-22): ban
dau file nay la "0031" vi luc viet head la 0030. Trong luc do main merge
0031_remove_better_auth_and_add_supabase_uid.py CUNG lay so 0031 -> 2 file
trung revision id, alembic bao "Revision 0031 is present more than once" va
gay 2 head, hong ca chuoi migration. Doi thanh "0032" (xep sau 0031) de va lan
1. Sau do main lai merge THEM 0032_rag_corpus_recovery.py (cung tu "0032" ->
lap lai dung y het loi cu). Doi thanh "0038" (xep sau chuoi 0032(rag)..0037
cua main) - VAN TRUNG, vi main lai merge THEM 0038_drug_request.py cung luc
(2 nhanh khac nhau cung xin so "0038" tu head luc do). Lan nay doi thanh
"0041", xep sau CA 0038_drug_request.py VA 0039_agent_feedback_ticket.py -
CO Y bo qua so "0040": luc phat hien loi nay, DB production dang ghi
alembic_version='0040' nhung KHONG co file nao trong lich su git tung mang
revision do (rat co the tu 1 lan chay migration cuc bo truoc day chua bao
gio duoc commit) - tranh dung lai đung so do de khoi gay nham lan them, de
team co quyen truy cap DB that tu xu ly rieng viec "0040 mo coi" nay. Khong
doi lai so cua main (0038_drug_request.py/0039) vi ly do tuong tu lan truoc -
doi 1 file nay van la it cham nhat.

Revision ID: 0041
Revises: 0039
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0039"
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
