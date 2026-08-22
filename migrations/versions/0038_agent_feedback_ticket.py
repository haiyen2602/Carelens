"""Create agent_feedback_ticket table (BUILD-29 user report / issue tracking).

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-22

The migration is additive and reversible. Does not touch any existing
chat/Agent V2 data -- this table is written to only by the new
POST /agent/v2/feedback endpoint.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_feedback_ticket" not in inspector.get_table_names():
        op.create_table(
            "agent_feedback_ticket",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("actor_id", sa.String(), nullable=False),
            sa.Column("patient_id", sa.String(), nullable=False),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=True),
            sa.Column("agent_run_id", sa.String(), nullable=False),
            sa.Column("user_message", sa.Text(), nullable=False),
            sa.Column("assistant_message", sa.Text(), nullable=False),
            sa.Column("reason", sa.String(), nullable=False),
            sa.Column("user_note", sa.Text(), nullable=True),
            sa.Column("chatbot_version", sa.String(), nullable=False, server_default="agent-v2"),
            sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
            sa.Column("priority", sa.String(), nullable=False),
            sa.Column("p0_review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("admin_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(conn)
    existing_indexes = (
        [idx["name"] for idx in inspector.get_indexes("agent_feedback_ticket")]
        if "agent_feedback_ticket" in inspector.get_table_names()
        else []
    )

    for idx_name, cols, unique in [
        ("uq_agent_feedback_ticket_actor_run_reason", ["actor_id", "agent_run_id", "reason"], True),
        ("ix_agent_feedback_ticket_status_created", ["status", "created_at"], False),
        ("ix_agent_feedback_ticket_priority_created", ["priority", "created_at"], False),
        ("ix_agent_feedback_ticket_conversation", ["conversation_id"], False),
        ("ix_agent_feedback_ticket_chatbot_version", ["chatbot_version"], False),
    ]:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "agent_feedback_ticket", cols, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_feedback_ticket" in inspector.get_table_names():
        op.drop_table("agent_feedback_ticket")
