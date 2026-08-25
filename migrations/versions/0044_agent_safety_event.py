"""BUILD-34: canonical durable Safety/Handoff monitoring event.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-25

Additive and reversible. Adds one new table, ``agent_safety_event`` -- one
row per Agent V2 run whose ``SafetyDecision.outcome`` was ``SAFETY_BLOCKED``
or ``HANDOFF_REQUIRED`` (a plain ``SAFE`` outcome gets no row). Written
best-effort, post-response, purely from an already-completed
``OrchestrationResult`` -- never changes Safety/Handoff runtime behavior.

Does not touch ``agent_run``, ``agent_run_span``, ``agent_run_evaluation``,
``agent_run_judge``, ``doctor_review_request``, or ``escalation``. See
``backend.db.models.AgentSafetyEvent`` for the full column-by-column
rationale and
chat-bot-build/build_cai_thien/BUILD-34-SAFETY-HANDOFF-MONITORING-REPORT.md.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("id", sa.String(), {"nullable": False}),
    ("agent_run_id", sa.String(), {"nullable": False}),
    ("trace_id", sa.String(), {"nullable": False}),
    ("conversation_id", sa.String(), {"nullable": True}),
    ("patient_id", sa.String(), {"nullable": True}),
    ("actor_id", sa.String(), {"nullable": True}),
    ("outcome", sa.String(), {"nullable": False}),
    ("reason_code", sa.String(), {"nullable": False}),
    ("severity", sa.String(), {"nullable": False}),
    ("severity_source", sa.String(), {"nullable": False}),
    ("safety_path", sa.String(), {"nullable": True}),
    ("provenance", sa.String(), {"nullable": True}),
    ("handoff_required", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("handoff_created", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("handoff_id", sa.String(), {"nullable": True}),
    ("handoff_status", sa.String(), {"nullable": True}),
    ("error_code", sa.String(), {"nullable": True}),
    ("evaluation_version", sa.String(), {"nullable": True}),
    ("created_at", sa.DateTime(timezone=True), {"nullable": False}),
    ("resolved_at", sa.DateTime(timezone=True), {"nullable": True}),
]

_INDEXES = [
    ("ix_agent_safety_event_agent_run_id", ["agent_run_id"], False),
    ("ix_agent_safety_event_trace_id", ["trace_id"], False),
    ("ix_agent_safety_event_patient_id", ["patient_id"], False),
    ("ix_agent_safety_event_handoff_id", ["handoff_id"], False),
    ("ix_agent_safety_event_severity_created", ["severity", "created_at"], False),
    ("ix_agent_safety_event_reason_code_created", ["reason_code", "created_at"], False),
    ("ix_agent_safety_event_created_at", ["created_at"], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_safety_event" not in inspector.get_table_names():
        op.create_table(
            "agent_safety_event",
            *[sa.Column(name, col_type, **kwargs) for name, col_type, kwargs in _COLUMNS],
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(conn)
    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_safety_event")}
        if "agent_safety_event" in inspector.get_table_names()
        else set()
    )
    for idx_name, cols, unique in _INDEXES:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "agent_safety_event", cols, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_safety_event" in inspector.get_table_names():
        op.drop_table("agent_safety_event")
