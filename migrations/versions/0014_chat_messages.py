"""Vong 3, muc 7.1 (chatbot-rag-design.md) - bang chat_messages: lich su
chat DAY DU cho hien thi (khac han cua so ngu canh 15 phut, muc 7.2 -
KHONG can bang rieng, doc lai chinh bang nay theo thoi gian). `hidden`
(soft-delete, quyet dinh #20) - "xoa doan chat" chi an, khong xoa that.

Index tren (patient_id, created_at) - phuc vu ca 2 truy van chinh: lay lich
su hien thi (loc patient_id, sap theo created_at) VA cua so ngu canh 15
phut (loc patient_id + created_at >= cutoff).

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-12

Doi so tu 0009 -> 0014 luc merge vong 3 vao main (2026-08-12): main da dung
0009-0013 cho patient/prescription_fields/photo_verification/account/
account_status (TASK-010-auth-api) truoc khi vong 3 merge - giu 1 chuoi
tuyen tinh duy nhat, khong co 2 nhanh "0009" khac noi dung."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_chat_messages_patient_id", "chat_messages", ["patient_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])
    op.create_index("ix_chat_messages_patient_id_created_at", "chat_messages", ["patient_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_patient_id_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_patient_id", table_name="chat_messages")
    op.drop_table("chat_messages")
