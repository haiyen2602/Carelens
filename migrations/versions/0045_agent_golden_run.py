"""BUILD-36: durable persistence for golden-evaluation runs + 2 ticket indexes.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-25

Additive and reversible. Adds two new tables:

  - ``agent_golden_run``: one row per BUILD-35 golden-evaluation run,
    written by that runner's own new optional ``--persist`` flag
    (``scripts/agent_v2/run_golden_evaluation.py``) -- BUILD-35 previously
    only ever wrote gitignored local JSON/Markdown files, which an Admin
    dashboard cannot query. Additive only: the JSON/Markdown output is
    completely unchanged, this is a second, durable copy of the same data.
  - ``agent_golden_run_case``: one row per golden case's result within one
    persisted run, so the dashboard can list/filter failed cases by
    category without parsing the parent row's JSON.

Also adds 2 indexes to the EXISTING ``agent_feedback_ticket`` table
(``trace_id``, ``agent_run_id``) -- a BUILD-36 audit finding: both columns
are already queried directly (``judge_result_out``,
``agent_safety_monitoring``'s ticket correlation) but neither was indexed.

Also adds 2 nullable columns to the EXISTING ``agent_run`` table
(``prompt_version``, ``retrieval_version``), stamped by
``_persist_durable_trace`` from ``settings.rag_prompt_version``/
``settings.rag_retriever_version`` at write time -- needed so the Versions
tab's before/after comparison (spec §13) is a real filter over durable
data, not a UI-only dropdown with no backend effect (the exact BUILD-25
bug class the spec explicitly calls out). NULL for every row written
before this migration -- never backfilled/guessed.

Does not touch ``agent_run``, ``agent_run_span``, ``agent_run_evaluation``,
``agent_run_judge``, ``agent_safety_event``, ``doctor_review_request``. See
``backend.db.models.AgentGoldenRun``/``AgentGoldenRunCase`` for the full
column-by-column rationale and
chat-bot-build/build_cai_thien/BUILD-36-ADMIN-MONITORING-DASHBOARD-V2-REPORT.md.
"""

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_RUN_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("id", sa.String(), {"nullable": False}),
    ("golden_set_version", sa.String(), {"nullable": False}),
    ("git_commit", sa.String(), {"nullable": False}),
    ("started_at", sa.String(), {"nullable": False}),
    ("completed_at", sa.String(), {"nullable": True}),
    ("total_cases", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("passed_cases", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("failed_cases", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("pass_rate", sa.Float(), {"nullable": True}),
    ("regression_gate_passed", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
    ("provenance_json", sa.JSON(), {"nullable": False, "server_default": "{}"}),
    ("aggregate_json", sa.JSON(), {"nullable": False, "server_default": "{}"}),
    ("regression_gate_json", sa.JSON(), {"nullable": False, "server_default": "{}"}),
    ("comparisons_json", sa.JSON(), {"nullable": False, "server_default": "[]"}),
    ("created_at", sa.DateTime(timezone=True), {"nullable": False}),
]

_RUN_INDEXES = [
    ("ix_agent_golden_run_golden_set_version", ["golden_set_version"], False),
    ("ix_agent_golden_run_created_at", ["created_at"], False),
]

_CASE_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("id", sa.String(), {"nullable": False}),
    ("run_id", sa.String(), {"nullable": False}),
    ("case_id", sa.String(), {"nullable": False}),
    ("category", sa.String(), {"nullable": False}),
    ("passed", sa.Boolean(), {"nullable": False}),
    ("checks_json", sa.JSON(), {"nullable": False, "server_default": "[]"}),
    ("created_at", sa.DateTime(timezone=True), {"nullable": False}),
]

_CASE_INDEXES = [
    ("ix_agent_golden_run_case_run_id", ["run_id"], False),
    ("ix_agent_golden_run_case_category_passed", ["category", "passed"], False),
]

_TICKET_INDEXES = [
    ("ix_agent_feedback_ticket_trace_id", ["trace_id"], False),
    ("ix_agent_feedback_ticket_agent_run_id", ["agent_run_id"], False),
]

_AGENT_RUN_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("prompt_version", sa.String(), {"nullable": True}),
    ("retrieval_version", sa.String(), {"nullable": True}),
]

_AGENT_RUN_NEW_INDEXES = [
    ("ix_agent_run_prompt_version", ["prompt_version"], False),
    ("ix_agent_run_retrieval_version", ["retrieval_version"], False),
]


def _create_table_if_missing(inspector: sa.Inspector, table_name: str, columns: list[tuple[str, sa.types.TypeEngine, dict]]) -> None:
    if table_name not in inspector.get_table_names():
        op.create_table(
            table_name,
            *[sa.Column(name, col_type, **kwargs) for name, col_type, kwargs in columns],
            sa.PrimaryKeyConstraint("id"),
        )


def _create_indexes_if_missing(conn: sa.engine.Connection, table_name: str, indexes: list[tuple[str, list[str], bool]]) -> None:
    inspector = sa.inspect(conn)
    if table_name not in inspector.get_table_names():
        return
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    for idx_name, cols, unique in indexes:
        if idx_name not in existing:
            op.create_index(idx_name, table_name, cols, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    _create_table_if_missing(inspector, "agent_golden_run", _RUN_COLUMNS)
    _create_indexes_if_missing(conn, "agent_golden_run", _RUN_INDEXES)

    inspector = sa.inspect(conn)
    _create_table_if_missing(inspector, "agent_golden_run_case", _CASE_COLUMNS)
    _create_indexes_if_missing(conn, "agent_golden_run_case", _CASE_INDEXES)

    _create_indexes_if_missing(conn, "agent_feedback_ticket", _TICKET_INDEXES)

    if "agent_run" in inspector.get_table_names():
        existing_agent_run_columns = {col["name"] for col in inspector.get_columns("agent_run")}
        for name, col_type, kwargs in _AGENT_RUN_NEW_COLUMNS:
            if name not in existing_agent_run_columns:
                op.add_column("agent_run", sa.Column(name, col_type, **kwargs))
    _create_indexes_if_missing(conn, "agent_run", _AGENT_RUN_NEW_INDEXES)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_agent_run_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_run")} if "agent_run" in inspector.get_table_names() else set()
    )
    for idx_name, _cols, _unique in _AGENT_RUN_NEW_INDEXES:
        if idx_name in existing_agent_run_indexes:
            op.drop_index(idx_name, table_name="agent_run")
    if "agent_run" in inspector.get_table_names():
        existing_agent_run_columns = {col["name"] for col in inspector.get_columns("agent_run")}
        for name, _col_type, _kwargs in _AGENT_RUN_NEW_COLUMNS:
            if name in existing_agent_run_columns:
                op.drop_column("agent_run", name)

    existing_ticket_indexes = (
        {idx["name"] for idx in inspector.get_indexes("agent_feedback_ticket")}
        if "agent_feedback_ticket" in inspector.get_table_names()
        else set()
    )
    for idx_name, _cols, _unique in _TICKET_INDEXES:
        if idx_name in existing_ticket_indexes:
            op.drop_index(idx_name, table_name="agent_feedback_ticket")

    if "agent_golden_run_case" in inspector.get_table_names():
        op.drop_table("agent_golden_run_case")
    if "agent_golden_run" in inspector.get_table_names():
        op.drop_table("agent_golden_run")
