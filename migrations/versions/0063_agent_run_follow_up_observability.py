"""BUILD-47: durable follow-up classifier outcome on ``agent_run``.

Revision ID: 0063
Revises: 0062
Create Date: 2026-08-29

Additive and reversible, same shape as 0042 (BUILD-32). BUILD-43 introduced
the deterministic follow-up taxonomy (``backend/agents/v2/follow_up.py``) that
decides whether a turn inherits the prior conversation topic/entity, and it
already emits that decision as an ``agent_context_resolution.completed``
telemetry event -- but the four attributes carrying the decision were never in
``backend.agents.v2.observability._ALLOWED_ATTRIBUTE_KEYS`` (silently dropped
before any sink), and the event is a bare marker with no ``latency_ms`` that
``_build_span_rows`` deliberately never turns into an ``AgentRunSpan`` row. So
there was no way -- log or DB -- to measure how often conversation context is
actually inherited versus lost.

These four columns close that gap. They exist for direct SQL analysis, e.g.

    SELECT follow_up_category, count(*) FROM agent_run
    WHERE follow_up_category IS NOT NULL GROUP BY 1;

NOT for the admin monitoring dashboard: no endpoint, service, or UI reads
them, and none is added here -- deliberately out of scope for this build.

NULL is the honest value for every turn that structurally never reaches the
classifier (schedule/safety/out-of-scope/doctor-review, plus any turn already
resolved by a suggested-action button), and for every row written before this
migration. No backfill, no guessed values, no other table touched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_AGENT_RUN_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, dict]] = [
    ("follow_up_category", sa.String(), {"nullable": True}),
    ("follow_up_reason_code", sa.String(), {"nullable": True}),
    ("follow_up_inherited_topic", sa.Boolean(), {"nullable": True}),
    ("follow_up_inherited_entity", sa.Boolean(), {"nullable": True}),
]

_AGENT_RUN_NEW_INDEXES = [
    ("ix_agent_run_follow_up_category_created", ["follow_up_category", "created_at"], False),
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


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("agent_run")}
    for idx_name, _cols, _unique in _AGENT_RUN_NEW_INDEXES:
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name="agent_run")

    existing_columns = {col["name"] for col in inspector.get_columns("agent_run")}
    for name, _col_type, _kwargs in reversed(_AGENT_RUN_NEW_COLUMNS):
        if name in existing_columns:
            op.drop_column("agent_run", name)
