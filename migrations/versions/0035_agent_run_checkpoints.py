"""Add durable sanitized Agent V2 execution checkpoints.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-18

The migration is additive. Checkpoints retain only bounded execution state and
reference metadata; model reasoning and raw clinical/chat content are excluded.

BUILD-24Q renumbering (2026-08-21): originally revision 0033 -- see
report 52-build-24q-main-branch-reconciliation.md. No change to DDL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_run_checkpoint",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("workflow_state", sa.String(), nullable=False),
        sa.Column("completed_tools", sa.JSON(), nullable=False),
        sa.Column("resolved_entities", sa.JSON(), nullable=False),
        sa.Column("verified_context_refs", sa.JSON(), nullable=False),
        sa.Column("safety_disposition", sa.String(), nullable=True),
        sa.Column("pending_action", sa.String(), nullable=False),
        sa.Column("terminal_status", sa.String(), nullable=True),
        sa.Column("lease_token", sa.String(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_agent_run_checkpoint_run", "agent_run_checkpoint", ["agent_run_id"], unique=True)
    op.create_index("ix_agent_run_checkpoint_pending_updated", "agent_run_checkpoint", ["pending_action", "updated_at"])
    op.create_index("ix_agent_run_checkpoint_terminal_updated", "agent_run_checkpoint", ["terminal_status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_run_checkpoint_terminal_updated", table_name="agent_run_checkpoint")
    op.drop_index("ix_agent_run_checkpoint_pending_updated", table_name="agent_run_checkpoint")
    op.drop_index("uq_agent_run_checkpoint_run", table_name="agent_run_checkpoint")
    op.drop_table("agent_run_checkpoint")
