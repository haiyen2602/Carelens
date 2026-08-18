"""Add DB-4D normalized scheduling schema.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-17

DB-4D is additive schema only. It keeps ``schedule_rule.times_of_day`` for
compatibility, does not generate dose occurrences, and intentionally defers
foreign-key/check/legacy-data hardening until operational validation.
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create normalized rule time/cycle structures and nullable context fields."""

    # Inclusive end-date semantics are established by DB-4D application and
    # migration documentation. The column remains a compatible ``date`` type.
    op.add_column("prescription_item", sa.Column("doses_per_day", sa.Integer(), nullable=True))
    op.add_column("prescription_item", sa.Column("meal_instruction_code", sa.String(), nullable=True))
    op.add_column("prescription_item", sa.Column("meal_instruction_text", sa.Text(), nullable=True))

    op.create_table(
        "schedule_rule_time",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("schedule_rule_id", sa.String(), nullable=False),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("schedule_rule_id", "local_time", name="uq_schedule_rule_time_local_time"),
    )
    # The unique constraint is also the required rule/time lookup index.

    op.create_table(
        "schedule_rule_cycle",
        sa.Column("schedule_rule_id", sa.String(), primary_key=True),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("on_days", sa.Integer(), nullable=False),
        sa.Column("off_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("dose_occurrence", sa.Column("scheduled_local_date", sa.Date(), nullable=True))
    op.add_column("dose_occurrence", sa.Column("scheduled_local_time", sa.Time(), nullable=True))
    op.add_column("dose_occurrence", sa.Column("timezone", sa.String(), nullable=True))
    op.create_index(
        "ix_dose_occurrence_patient_local_schedule",
        "dose_occurrence",
        ["patient_id", "scheduled_local_date", "scheduled_local_time"],
    )


def downgrade() -> None:
    """Remove DB-4D additive schema in reverse dependency order."""

    op.drop_index("ix_dose_occurrence_patient_local_schedule", table_name="dose_occurrence")
    op.drop_column("dose_occurrence", "timezone")
    op.drop_column("dose_occurrence", "scheduled_local_time")
    op.drop_column("dose_occurrence", "scheduled_local_date")

    op.drop_table("schedule_rule_cycle")
    op.drop_table("schedule_rule_time")

    op.drop_column("prescription_item", "meal_instruction_text")
    op.drop_column("prescription_item", "meal_instruction_code")
    op.drop_column("prescription_item", "doses_per_day")
