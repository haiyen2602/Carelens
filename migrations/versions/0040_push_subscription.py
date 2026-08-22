"""Bang push_subscription + push_reminder_sent - Web Push cho nhac gio uong
thuoc (THEM 2026-08-20). Xem ghi chu day du trong backend/db/models.py::
PushSubscription / PushReminderSent (vi sao endpoint UNIQUE, vi sao khoa
duy nhat cua push_reminder_sent la khung gio chu khong phai dose_event_id).

LUU Y ve revision chain (doi so 0031 -> 0032 -> 0038 -> 0040, 2026-08-22):
ban dau file nay la "0031" vi luc viet head la 0030. Trong luc do main merge
0031_remove_better_auth_and_add_supabase_uid.py CUNG lay so 0031 -> 2 file
trung revision id, alembic bao "Revision 0031 is present more than once" va
gay 2 head, hong ca chuoi migration. Doi thanh "0032" (xep sau 0031) de vá lan
1. Sau do main lai merge THEM 0032_rag_corpus_recovery.py (cung tu "0032" ->
lap lai dung y het loi cu). Doi thanh "0038" lan 2, xep sau chuoi 0032(rag)..
0037(system_audit_logs) cua main luc do.

LAN 3 (BUILD-30 prep, 2026-08-22, phat hien khi audit migration truoc khi mo
PR moi): trong luc file nay dang cho merge, CA
0038_drug_request.py (PR #89) LAN 0039_agent_feedback_ticket.py (PR #90, da
chain sau 0038_drug_request.py) deu da merge vao main truoc no - "0038" lai
trung lan nua voi drug_request.py (`alembic heads` bao chinh xac "Revision
0038 is present more than once", xac nhan bang cach chay that tren
origin/main). Doi thanh "0040" (xep sau 0039_agent_feedback_ticket.py, chuoi
dai nhat/moi merge gan day nhat) thay vi doi lai 0038_drug_request.py hay
0039 - cung nguyen tac da dung moi lan truoc: chuoi nao da co migration khac
xay len no thi giu nguyen, file con lai doi so.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
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
