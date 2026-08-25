"""BUILD-33: durable production LLM Judge V2 results.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-25

Additive and reversible. Adds one new table, ``agent_run_judge`` -- a
sampled/ticketed/anomalous subset of Agent V2 runs get exactly one row per
(agent_run_id, judge_model, rubric_version, judge_prompt_version) tuple,
enqueued synchronously (``JUDGE_PENDING``, no LLM call yet) right after
``AgentRunEvaluation`` is persisted, then scored out-of-band by a background
worker (``backend.services.agent_judge_worker``) polled off the existing
shared APScheduler (``backend.services.escalation_scheduler``) -- never in
the synchronous chat request/response path.

Does not touch ``agent_run``, ``agent_run_span``, ``agent_run_evaluation``,
or any Agent V2 routing/safety/response behavior. See
``backend.db.models.AgentRunJudge`` for the full column-by-column rationale
and chat-bot-build/build_cai_thien/BUILD-33-PRODUCTION-JUDGE-V2-REPORT.md.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("id", sa.String(), {"nullable": False}),
    ("agent_run_id", sa.String(), {"nullable": False}),
    ("trace_id", sa.String(), {"nullable": False}),
    ("judge_status", sa.String(), {"nullable": False, "server_default": "JUDGE_PENDING"}),
    ("eligibility_reason", sa.String(), {"nullable": False}),
    ("priority", sa.Integer(), {"nullable": False, "server_default": "4"}),
    ("execution_path", sa.String(), {"nullable": True}),
    ("judge_provider", sa.String(), {"nullable": False}),
    ("judge_model", sa.String(), {"nullable": False}),
    ("judge_config_json", sa.JSON(), {"nullable": False}),
    ("rubric_name", sa.String(), {"nullable": False}),
    ("rubric_version", sa.String(), {"nullable": False}),
    ("judge_prompt_version", sa.String(), {"nullable": False}),
    ("evaluation_version", sa.String(), {"nullable": True}),
    ("overall_score", sa.Float(), {"nullable": True}),
    ("dimension_scores_json", sa.JSON(), {"nullable": False}),
    ("flags_json", sa.JSON(), {"nullable": False}),
    ("confidence", sa.Float(), {"nullable": True}),
    ("failure_reason", sa.String(), {"nullable": True}),
    ("input_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("output_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("cost_usd", sa.Float(), {"nullable": True}),
    ("cost_status", sa.String(), {"nullable": False, "server_default": "NOT_AVAILABLE"}),
    ("sanitized_query", sa.Text(), {"nullable": True}),
    ("sanitized_response", sa.Text(), {"nullable": True}),
    ("sanitized_context_json", sa.JSON(), {"nullable": False}),
    ("created_at", sa.DateTime(timezone=True), {"nullable": False}),
    ("evaluated_at", sa.DateTime(timezone=True), {"nullable": True}),
]

_INDEXES = [
    (
        "uq_agent_run_judge_run_model_rubric_prompt",
        ["agent_run_id", "judge_model", "rubric_version", "judge_prompt_version"],
        True,
    ),
    ("ix_agent_run_judge_trace_id", ["trace_id"], False),
    ("ix_agent_run_judge_status_priority_created", ["judge_status", "priority", "created_at"], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_run_judge" not in inspector.get_table_names():
        op.create_table(
            "agent_run_judge",
            *[sa.Column(name, col_type, **kwargs) for name, col_type, kwargs in _COLUMNS],
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(conn)
    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_run_judge")}
        if "agent_run_judge" in inspector.get_table_names()
        else set()
    )
    for idx_name, cols, unique in _INDEXES:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "agent_run_judge", cols, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_run_judge" in inspector.get_table_names():
        op.drop_table("agent_run_judge")
