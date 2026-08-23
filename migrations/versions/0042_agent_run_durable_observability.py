"""BUILD-32: durable observability columns/tables for Agent V2 runs.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-23

Additive and reversible. Adds nullable/defaulted columns to the existing
``agent_run`` table (token usage, cost + pricing version, duration, timeout,
canonical error code, empty-reply flag, evaluation version -- previously this
data was computed correctly by Agent V2 but only ever reached an in-memory
ring buffer capped at 200 traces and reset on every restart/deploy, see
backend/services/telemetry.py) plus two new tables:

  - ``agent_run_span``: real per-step timing (router/model/tool/retrieval/
    safety/handoff/checkpoint/guardrail/runtime/time_query/grounding/
    evaluation), captured live during the actual orchestrator/runtime call
    and persisted best-effort right after the response commits (see
    ``backend.agents.v2.observability.BufferingSink`` and
    ``backend.api.agent_v2_routes._persist_durable_trace``).
  - ``agent_run_evaluation``: durable Evaluation V2 result, previously only
    ever written into the ring buffer's trace metadata.

Existing rows in ``agent_run`` get the column defaults (0 / False /
'NOT_AVAILABLE' / 'USD'); no backfill, no data loss to any other table. Does
not touch Agent V2's own routing/safety/response behavior -- write paths only.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_AGENT_RUN_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("trace_id", sa.String(), {"nullable": True}),
    ("actor_id", sa.String(), {"nullable": True}),
    ("input_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("cached_input_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("output_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("total_tokens", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("model_calls", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("model", sa.String(), {"nullable": True}),
    ("pricing_version", sa.String(), {"nullable": True}),
    ("input_cost_usd", sa.Float(), {"nullable": True}),
    ("output_cost_usd", sa.Float(), {"nullable": True}),
    ("total_cost_usd", sa.Float(), {"nullable": True}),
    ("cost_status", sa.String(), {"nullable": False, "server_default": "NOT_AVAILABLE"}),
    ("currency", sa.String(), {"nullable": False, "server_default": "USD"}),
    ("duration_ms", sa.Float(), {"nullable": True}),
    ("timeout", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("error_code", sa.String(), {"nullable": True}),
    ("empty_reply", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("evaluation_version", sa.String(), {"nullable": True}),
]

_AGENT_RUN_NEW_INDEXES = [
    ("ix_agent_run_trace_id", ["trace_id"], False),
    ("ix_agent_run_status_created", ["status", "created_at"], False),
    ("ix_agent_run_error_code_created", ["error_code", "created_at"], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_columns = {col["name"] for col in inspector.get_columns("agent_run")}
    for name, col_type, kwargs in _AGENT_RUN_NEW_COLUMNS:
        if name not in existing_columns:
            op.add_column("agent_run", sa.Column(name, col_type, **kwargs))

    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("agent_run")}
    for idx_name, cols, unique in _AGENT_RUN_NEW_INDEXES:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "agent_run", cols, unique=unique)

    if "agent_run_span" not in inspector.get_table_names():
        op.create_table(
            "agent_run_span",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("agent_run_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("span_name", sa.String(), nullable=False),
            sa.Column("span_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="OK"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "agent_run_evaluation" not in inspector.get_table_names():
        op.create_table(
            "agent_run_evaluation",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("agent_run_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("evaluation_version", sa.String(), nullable=False),
            sa.Column("execution_path", sa.String(), nullable=True),
            sa.Column("metrics_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(conn)
    span_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_run_span")}
        if "agent_run_span" in inspector.get_table_names()
        else set()
    )
    for idx_name, cols, unique in [
        ("ix_agent_run_span_run_started", ["agent_run_id", "started_at"], False),
        ("ix_agent_run_span_trace_id", ["trace_id"], False),
        ("ix_agent_run_span_type_started", ["span_type", "started_at"], False),
    ]:
        if idx_name not in span_indexes:
            op.create_index(idx_name, "agent_run_span", cols, unique=unique)

    eval_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_run_evaluation")}
        if "agent_run_evaluation" in inspector.get_table_names()
        else set()
    )
    for idx_name, cols, unique in [
        ("uq_agent_run_evaluation_agent_run_id", ["agent_run_id"], True),
        ("ix_agent_run_evaluation_trace_id", ["trace_id"], False),
    ]:
        if idx_name not in eval_indexes:
            op.create_index(idx_name, "agent_run_evaluation", cols, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "agent_run_evaluation" in inspector.get_table_names():
        op.drop_table("agent_run_evaluation")
    if "agent_run_span" in inspector.get_table_names():
        op.drop_table("agent_run_span")

    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("agent_run")}
    for idx_name, _cols, _unique in _AGENT_RUN_NEW_INDEXES:
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name="agent_run")

    existing_columns = {col["name"] for col in inspector.get_columns("agent_run")}
    for name, _col_type, _kwargs in reversed(_AGENT_RUN_NEW_COLUMNS):
        if name in existing_columns:
            op.drop_column("agent_run", name)
