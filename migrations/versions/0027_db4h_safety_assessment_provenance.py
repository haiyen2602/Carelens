"""Add provenance snapshots to DB-4H safety assessments.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-17

The policy relationship alone is insufficient for an immutable assessment:
policy source/review status may change later.  Nullable additive snapshots keep
old assessments auditable without hardening legacy or backfilled rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add safety-policy provenance snapshots to missed/delayed assessments."""

    op.add_column("missed_dose_assessment", sa.Column("policy_source_type", sa.String(), nullable=True))
    op.add_column("missed_dose_assessment", sa.Column("policy_review_status", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove DB-4H-only additive assessment fields."""

    op.drop_column("missed_dose_assessment", "policy_review_status")
    op.drop_column("missed_dose_assessment", "policy_source_type")
