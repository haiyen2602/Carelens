"""Add Database Architecture V2 additive schema.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-17

DB-4A only:
- Keep all legacy tables/data.
- Do not redefine legacy `dose_event`.
- Use `dose_event_log` for V2 immutable events during migration.
- Keep backfill-dependent columns nullable.
- Do not import Drug V2, backfill, dual-write, cut over, or deploy.

Renumbered from 0023 -> 0025 (down_revision 0022 -> 0024): 0023/0024 were
taken by 0023_patient_profile_fields.py -> 0024_doctor_watch.py, merged
into main after this migration was originally drafted. Local dev DB was
still at alembic_version 0022 (this migration had never been stamped) when
renumbered, so no DB-side fix was needed - see git history for the original
0023 file if needed.

Renumbered again from 0025 -> 0027 (down_revision 0024 -> 0026) when merging
`main` into this branch on 2026-08-18: main had independently taken 0025
(`0025_better_auth_tables.py`) and 0026 (`0026_normalize_account_email.py`)
for the auth/OAuth work. Same situation as above - this migration had not
been stamped anywhere, so only the revision ids move, no data impact.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive columns on legacy tables. All nullable until validation/backfill.
    op.add_column("patient", sa.Column("user_id", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("sex", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("timezone", sa.String(), nullable=True))
    op.add_column("patient", sa.Column("status", sa.String(), nullable=True))
    op.create_index("ix_patient_user_id", "patient", ["user_id"])

    op.add_column("prescription", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("prescription", sa.Column("prescribed_by", sa.String(), nullable=True))
    op.add_column("prescription", sa.Column("prescribed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prescription", sa.Column("source_type", sa.String(), nullable=True))
    op.create_index("ix_prescription_prescribed_by", "prescription", ["prescribed_by"])

    # Drug Knowledge V2 identity/reference tables. Empty in DB-4A; import is DB-4B.
    op.create_table(
        "drug_product",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("legacy_drug_id", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("dosage_form", sa.String(), nullable=True),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("strength_text", sa.String(), nullable=True),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_drug_product_legacy_drug_id", "drug_product", ["legacy_drug_id"], unique=True)
    op.create_index("ix_drug_product_category_id", "drug_product", ["category_id"])
    op.create_index("ix_drug_product_display_name", "drug_product", ["display_name"])

    op.create_table(
        "drug_id_map",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("legacy_drug_id", sa.String(), nullable=False),
        sa.Column("drug_product_id", sa.String(), nullable=False),
        sa.Column("mapping_status", sa.String(), nullable=False),
        sa.Column("source_manifest_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drug_id_map_drug_product_id", "drug_id_map", ["drug_product_id"])
    op.create_index("ix_drug_id_map_mapping_status", "drug_id_map", ["mapping_status"])
    op.create_index(
        "uq_drug_id_map_active_legacy",
        "drug_id_map",
        ["legacy_drug_id"],
        unique=True,
        postgresql_where=sa.text("mapping_status = 'ACTIVE'"),
    )

    op.create_table(
        "ingredient",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingredient_name", "ingredient", ["name"])

    op.create_table(
        "drug_product_ingredient",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drug_product_id", sa.String(), nullable=False),
        sa.Column("ingredient_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("drug_product_id", "ingredient_id", name="uq_drug_product_ingredient_pair"),
    )
    op.create_index("ix_drug_product_ingredient_drug_product_id", "drug_product_ingredient", ["drug_product_id"])
    op.create_index("ix_drug_product_ingredient_ingredient_id", "drug_product_ingredient", ["ingredient_id"])

    # Prescription / medication scheduling V2.
    op.create_table(
        "prescription_item",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("prescription_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("legacy_drug_id", sa.String(), nullable=True),
        sa.Column("drug_display_name", sa.String(), nullable=True),
        sa.Column("dose_text", sa.Text(), nullable=True),
        sa.Column("dose_value", sa.Numeric(), nullable=True),
        sa.Column("dose_unit", sa.String(), nullable=True),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("frequency_text", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("migration_source", sa.String(), nullable=True),
        sa.Column("migration_source_id", sa.String(), nullable=True),
        sa.Column("migration_item_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prescription_item_prescription_id", "prescription_item", ["prescription_id"])
    op.create_index("ix_prescription_item_patient_status", "prescription_item", ["patient_id", "status"])
    op.create_index("ix_prescription_item_drug_product_id", "prescription_item", ["drug_product_id"])
    op.create_index("ix_prescription_item_legacy_drug_id", "prescription_item", ["legacy_drug_id"])
    op.create_index(
        "uq_prescription_item_migration_source",
        "prescription_item",
        ["migration_source", "migration_source_id", "migration_item_index"],
        unique=True,
    )

    op.create_table(
        "medication_plan",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("prescription_item_id", sa.String(), nullable=True),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("legacy_drug_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_medication_plan_patient_status", "medication_plan", ["patient_id", "status"])
    op.create_index("ix_medication_plan_prescription_item_id", "medication_plan", ["prescription_item_id"])
    op.create_index("ix_medication_plan_drug_product_id", "medication_plan", ["drug_product_id"])

    op.create_table(
        "schedule_rule",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("medication_plan_id", sa.String(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column("interval_value", sa.Integer(), nullable=True),
        sa.Column("interval_unit", sa.String(), nullable=True),
        sa.Column("times_of_day", sa.JSON(), nullable=True),
        sa.Column("days_of_week", sa.JSON(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedule_rule_medication_plan_status", "schedule_rule", ["medication_plan_id", "status"])
    op.create_index("ix_schedule_rule_status_window", "schedule_rule", ["status", "start_at", "end_at"])

    op.create_table(
        "dose_occurrence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("medication_plan_id", sa.String(), nullable=True),
        sa.Column("prescription_item_id", sa.String(), nullable=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("legacy_drug_id", sa.String(), nullable=True),
        sa.Column("schedule_rule_id", sa.String(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_key", sa.String(), nullable=False),
        sa.Column("legacy_dose_event_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("generation_key", name="uq_dose_occurrence_generation_key"),
    )
    op.create_index("ix_dose_occurrence_medication_plan_scheduled", "dose_occurrence", ["medication_plan_id", "scheduled_at"])
    op.create_index("ix_dose_occurrence_patient_scheduled", "dose_occurrence", ["patient_id", "scheduled_at"])
    op.create_index("ix_dose_occurrence_status_scheduled", "dose_occurrence", ["status", "scheduled_at"])
    op.create_index("ix_dose_occurrence_patient_status_scheduled", "dose_occurrence", ["patient_id", "status", "scheduled_at"])
    op.create_index("ix_dose_occurrence_drug_product_id", "dose_occurrence", ["drug_product_id"])
    op.create_index("ix_dose_occurrence_legacy_drug_scheduled", "dose_occurrence", ["legacy_drug_id", "scheduled_at"])
    op.create_index("ix_dose_occurrence_legacy_dose_event_id", "dose_occurrence", ["legacy_dose_event_id"])

    op.create_table(
        "dose_event_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dose_occurrence_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("medication_plan_id", sa.String(), nullable=True),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_dose_event_log_idempotency_key", "dose_event_log", ["idempotency_key"], unique=True)
    op.create_index("ix_dose_event_log_occurrence_created", "dose_event_log", ["dose_occurrence_id", "created_at"])
    op.create_index("ix_dose_event_log_patient_event_at", "dose_event_log", ["patient_id", "event_at"])
    op.create_index("ix_dose_event_log_event_type_event_at", "dose_event_log", ["event_type", "event_at"])
    op.create_index("ix_dose_event_log_plan_event_at", "dose_event_log", ["medication_plan_id", "event_at"])

    # Notification and safety V2.
    op.create_table(
        "notification_job",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("dose_occurrence_id", sa.String(), nullable=True),
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("recipient_type", sa.String(), nullable=False),
        sa.Column("recipient_id", sa.String(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_job_idempotency_key"),
    )
    op.create_index("ix_notification_job_dose_occurrence_id", "notification_job", ["dose_occurrence_id"])
    op.create_index("ix_notification_job_status_scheduled", "notification_job", ["status", "scheduled_at"])
    op.create_index("ix_notification_job_patient_scheduled", "notification_job", ["patient_id", "scheduled_at"])
    op.create_index("ix_notification_job_recipient_status", "notification_job", ["recipient_type", "recipient_id", "status"])
    op.create_index("ix_notification_job_provider_message", "notification_job", ["provider", "provider_message_id"])

    op.create_table(
        "medication_safety_policy",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("risk_type", sa.String(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("action_policy", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope_type", "scope_id", "risk_type", "policy_version", name="uq_medication_safety_policy_version"),
    )
    op.create_index("ix_medication_safety_policy_scope_risk", "medication_safety_policy", ["scope_type", "scope_id", "risk_type"])
    op.create_index("ix_medication_safety_policy_risk_review", "medication_safety_policy", ["risk_type", "review_status"])
    op.create_index("ix_medication_safety_policy_valid_window", "medication_safety_policy", ["valid_from", "valid_to"])
    op.create_index(
        "ix_medication_safety_policy_reviewed_scope",
        "medication_safety_policy",
        ["scope_type", "scope_id", "risk_type"],
        postgresql_where=sa.text("review_status = 'REVIEWED'"),
    )
    op.create_index(
        "ix_medication_safety_policy_legacy_scope",
        "medication_safety_policy",
        ["scope_type", "scope_id", "risk_type"],
        postgresql_where=sa.text("source_type = 'LEGACY_CATEGORY_RULE'"),
    )

    op.create_table(
        "missed_dose_assessment",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("dose_occurrence_id", sa.String(), nullable=False),
        sa.Column("medication_plan_id", sa.String(), nullable=True),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("risk_type", sa.String(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("recommended_action", sa.String(), nullable=False),
        sa.Column("policy_id", sa.String(), nullable=True),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("assessment_version", sa.String(), nullable=False),
        sa.Column("evaluator", sa.String(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_missed_dose_assessment_idempotency_key", "missed_dose_assessment", ["idempotency_key"], unique=True)
    op.create_index("ix_missed_dose_assessment_occurrence_evaluated", "missed_dose_assessment", ["dose_occurrence_id", "evaluated_at"])
    op.create_index("ix_missed_dose_assessment_patient_evaluated", "missed_dose_assessment", ["patient_id", "evaluated_at"])
    op.create_index("ix_missed_dose_assessment_policy_id", "missed_dose_assessment", ["policy_id"])
    op.create_index("ix_missed_dose_assessment_risk_level_time", "missed_dose_assessment", ["risk_type", "risk_level", "evaluated_at"])

    op.create_table(
        "safety_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("dose_occurrence_id", sa.String(), nullable=True),
        sa.Column("drug_product_id", sa.String(), nullable=True),
        sa.Column("missed_dose_assessment_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_safety_event_idempotency_key", "safety_event", ["idempotency_key"], unique=True)
    op.create_index("ix_safety_event_patient_created", "safety_event", ["patient_id", "created_at"])
    op.create_index("ix_safety_event_type_created", "safety_event", ["event_type", "created_at"])
    op.create_index("ix_safety_event_severity_created", "safety_event", ["severity", "created_at"])
    op.create_index("ix_safety_event_dose_occurrence_id", "safety_event", ["dose_occurrence_id"])
    op.create_index("ix_safety_event_assessment_id", "safety_event", ["missed_dose_assessment_id"])

    # Conversation and agent audit V2.
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_patient_started", "conversation", ["patient_id", "started_at"])
    op.create_index("ix_conversation_status_last_message", "conversation", ["status", "last_message_at"])

    op.create_table(
        "message",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_message_conversation_created", "message", ["conversation_id", "created_at"])

    op.create_table(
        "agent_run",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("patient_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_run_request_id", "agent_run", ["request_id"])
    op.create_index("ix_agent_run_conversation_started", "agent_run", ["conversation_id", "started_at"])
    op.create_index("ix_agent_run_patient_started", "agent_run", ["patient_id", "started_at"])

    op.create_table(
        "agent_tool_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("input_reference", sa.JSON(), nullable=True),
        sa.Column("output_reference", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_tool_event_run_created", "agent_tool_event", ["agent_run_id", "created_at"])
    op.create_index("ix_agent_tool_event_tool_created", "agent_tool_event", ["tool_name", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_tool_event_tool_created", table_name="agent_tool_event")
    op.drop_index("ix_agent_tool_event_run_created", table_name="agent_tool_event")
    op.drop_table("agent_tool_event")

    op.drop_index("ix_agent_run_patient_started", table_name="agent_run")
    op.drop_index("ix_agent_run_conversation_started", table_name="agent_run")
    op.drop_index("ix_agent_run_request_id", table_name="agent_run")
    op.drop_table("agent_run")

    op.drop_index("ix_message_conversation_created", table_name="message")
    op.drop_table("message")

    op.drop_index("ix_conversation_status_last_message", table_name="conversation")
    op.drop_index("ix_conversation_patient_started", table_name="conversation")
    op.drop_table("conversation")

    op.drop_index("ix_safety_event_assessment_id", table_name="safety_event")
    op.drop_index("ix_safety_event_dose_occurrence_id", table_name="safety_event")
    op.drop_index("ix_safety_event_severity_created", table_name="safety_event")
    op.drop_index("ix_safety_event_type_created", table_name="safety_event")
    op.drop_index("ix_safety_event_patient_created", table_name="safety_event")
    op.drop_index("uq_safety_event_idempotency_key", table_name="safety_event")
    op.drop_table("safety_event")

    op.drop_index("ix_missed_dose_assessment_risk_level_time", table_name="missed_dose_assessment")
    op.drop_index("ix_missed_dose_assessment_policy_id", table_name="missed_dose_assessment")
    op.drop_index("ix_missed_dose_assessment_patient_evaluated", table_name="missed_dose_assessment")
    op.drop_index("ix_missed_dose_assessment_occurrence_evaluated", table_name="missed_dose_assessment")
    op.drop_index("uq_missed_dose_assessment_idempotency_key", table_name="missed_dose_assessment")
    op.drop_table("missed_dose_assessment")

    op.drop_index("ix_medication_safety_policy_legacy_scope", table_name="medication_safety_policy")
    op.drop_index("ix_medication_safety_policy_reviewed_scope", table_name="medication_safety_policy")
    op.drop_index("ix_medication_safety_policy_valid_window", table_name="medication_safety_policy")
    op.drop_index("ix_medication_safety_policy_risk_review", table_name="medication_safety_policy")
    op.drop_index("ix_medication_safety_policy_scope_risk", table_name="medication_safety_policy")
    op.drop_table("medication_safety_policy")

    op.drop_index("ix_notification_job_provider_message", table_name="notification_job")
    op.drop_index("ix_notification_job_recipient_status", table_name="notification_job")
    op.drop_index("ix_notification_job_patient_scheduled", table_name="notification_job")
    op.drop_index("ix_notification_job_status_scheduled", table_name="notification_job")
    op.drop_index("ix_notification_job_dose_occurrence_id", table_name="notification_job")
    op.drop_table("notification_job")

    op.drop_index("ix_dose_event_log_plan_event_at", table_name="dose_event_log")
    op.drop_index("ix_dose_event_log_event_type_event_at", table_name="dose_event_log")
    op.drop_index("ix_dose_event_log_patient_event_at", table_name="dose_event_log")
    op.drop_index("ix_dose_event_log_occurrence_created", table_name="dose_event_log")
    op.drop_index("uq_dose_event_log_idempotency_key", table_name="dose_event_log")
    op.drop_table("dose_event_log")

    op.drop_index("ix_dose_occurrence_legacy_dose_event_id", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_legacy_drug_scheduled", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_drug_product_id", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_patient_status_scheduled", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_status_scheduled", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_patient_scheduled", table_name="dose_occurrence")
    op.drop_index("ix_dose_occurrence_medication_plan_scheduled", table_name="dose_occurrence")
    op.drop_table("dose_occurrence")

    op.drop_index("ix_schedule_rule_status_window", table_name="schedule_rule")
    op.drop_index("ix_schedule_rule_medication_plan_status", table_name="schedule_rule")
    op.drop_table("schedule_rule")

    op.drop_index("ix_medication_plan_drug_product_id", table_name="medication_plan")
    op.drop_index("ix_medication_plan_prescription_item_id", table_name="medication_plan")
    op.drop_index("ix_medication_plan_patient_status", table_name="medication_plan")
    op.drop_table("medication_plan")

    op.drop_index("uq_prescription_item_migration_source", table_name="prescription_item")
    op.drop_index("ix_prescription_item_legacy_drug_id", table_name="prescription_item")
    op.drop_index("ix_prescription_item_drug_product_id", table_name="prescription_item")
    op.drop_index("ix_prescription_item_patient_status", table_name="prescription_item")
    op.drop_index("ix_prescription_item_prescription_id", table_name="prescription_item")
    op.drop_table("prescription_item")

    op.drop_index("ix_drug_product_ingredient_ingredient_id", table_name="drug_product_ingredient")
    op.drop_index("ix_drug_product_ingredient_drug_product_id", table_name="drug_product_ingredient")
    op.drop_table("drug_product_ingredient")

    op.drop_index("ix_ingredient_name", table_name="ingredient")
    op.drop_table("ingredient")

    op.drop_index("uq_drug_id_map_active_legacy", table_name="drug_id_map")
    op.drop_index("ix_drug_id_map_mapping_status", table_name="drug_id_map")
    op.drop_index("ix_drug_id_map_drug_product_id", table_name="drug_id_map")
    op.drop_table("drug_id_map")

    op.drop_index("ix_drug_product_display_name", table_name="drug_product")
    op.drop_index("ix_drug_product_category_id", table_name="drug_product")
    op.drop_index("uq_drug_product_legacy_drug_id", table_name="drug_product")
    op.drop_table("drug_product")

    op.drop_index("ix_prescription_prescribed_by", table_name="prescription")
    op.drop_column("prescription", "source_type")
    op.drop_column("prescription", "prescribed_at")
    op.drop_column("prescription", "prescribed_by")
    op.drop_column("prescription", "end_date")

    op.drop_index("ix_patient_user_id", table_name="patient")
    op.drop_column("patient", "status")
    op.drop_column("patient", "timezone")
    op.drop_column("patient", "sex")
    op.drop_column("patient", "display_name")
    op.drop_column("patient", "user_id")
