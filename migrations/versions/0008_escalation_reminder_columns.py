"""Vong 2, muc 13 (chatbot-rag-design.md) - cot moi cho co che nhac lai
escalation theo thoi gian: reminder_count (bat dau=1, tinh ca lan gui t=0),
last_reminder_at, resolved_at, resolved_by.

KHONG them cot `resolved: bool` rieng - `escalation.status` DA CO SAN
(OPEN|ACKED|RESOLVED, api-contracts.md §6) tu Phase 6 nhung chua tung duoc
dung - tai su dung lam tin hieu dung/khong dung nhac lai, tranh 2 truong
trang thai song song de lech nhau (dung loai bug da bat duoc o
ConversationState.safety_flag vs ConversationChatResponse.safety_flag truoc
day trong du an nay).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("escalation", sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("escalation", sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("escalation", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("escalation", sa.Column("resolved_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("escalation", "resolved_by")
    op.drop_column("escalation", "resolved_at")
    op.drop_column("escalation", "last_reminder_at")
    op.drop_column("escalation", "reminder_count")