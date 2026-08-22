"""Add HTTP-level Agent V2 idempotency key replay table.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-22

The migration is additive. This table is distinct from
``agent_run_checkpoint`` (crash-recovery resume of an in-flight run): it lets
a retried /agent/v2/orchestrate HTTP call for an already-finished run get
back the identical response without the orchestrator running again.

BUILD-24Q renumbering (2026-08-21): originally revision 0034 -- see
report 52-build-24q-main-branch-reconciliation.md. No change to DDL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_idempotency_key",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_agent_idempotency_key_actor_patient_key",
        "agent_idempotency_key",
        ["actor_id", "patient_id", "idempotency_key"],
        unique=True,
    )
    op.create_index("ix_agent_idempotency_key_expires_at", "agent_idempotency_key", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_idempotency_key_expires_at", table_name="agent_idempotency_key")
    op.drop_index("uq_agent_idempotency_key_actor_patient_key", table_name="agent_idempotency_key")
    op.drop_table("agent_idempotency_key")
