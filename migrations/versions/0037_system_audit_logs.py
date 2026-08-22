"""Create system_audit_logs table.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-22

The migration is additive. Bảng system_audit_logs lưu nhật ký kiểm toán hệ thống
cho các thao tác quản trị viên và các vai trò khác (append-only).
"""

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "system_audit_logs" not in tables:
        op.create_table(
            "system_audit_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("actor_id", sa.String(), nullable=True),
            sa.Column("actor_name", sa.String(), nullable=False),
            sa.Column("actor_role", sa.String(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("target", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # Re-inspect indexes
    inspector = sa.inspect(conn)
    existing_indexes = (
        [idx["name"] for idx in inspector.get_indexes("system_audit_logs")]
        if "system_audit_logs" in inspector.get_table_names()
        else []
    )

    for idx_name, cols in [
        ("ix_system_audit_logs_actor_id", ["actor_id"]),
        ("ix_system_audit_logs_actor_role", ["actor_role"]),
        ("ix_system_audit_logs_target", ["target"]),
        ("ix_system_audit_logs_created_at", ["created_at"]),
    ]:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "system_audit_logs", cols)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "system_audit_logs" in inspector.get_table_names():
        op.drop_table("system_audit_logs")
