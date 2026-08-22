"""Create agent_activity_snapshot table (BUILD-30 user-visible activity timeline).

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-22

The migration is additive and reversible. Does not touch any existing
chat/Agent V2/feedback-ticket data -- this table is written to only by the
best-effort, post-response activity-snapshot step in
backend/api/agent_v2_routes.py (see backend/services/agent_activity.py).
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_activity_snapshot" not in inspector.get_table_names():
        op.create_table(
            "agent_activity_snapshot",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("agent_run_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=True),
            sa.Column("patient_id", sa.String(), nullable=False),
            sa.Column("actor_id", sa.String(), nullable=False),
            sa.Column("intent", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("model_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activities_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(conn)
    existing_indexes = (
        [idx["name"] for idx in inspector.get_indexes("agent_activity_snapshot")]
        if "agent_activity_snapshot" in inspector.get_table_names()
        else []
    )

    for idx_name, cols, unique in [
        ("uq_agent_activity_snapshot_agent_run_id", ["agent_run_id"], True),
        ("ix_agent_activity_snapshot_trace_id", ["trace_id"], False),
        ("ix_agent_activity_snapshot_patient_created", ["patient_id", "created_at"], False),
    ]:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "agent_activity_snapshot", cols, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_activity_snapshot" in inspector.get_table_names():
        op.drop_table("agent_activity_snapshot")
