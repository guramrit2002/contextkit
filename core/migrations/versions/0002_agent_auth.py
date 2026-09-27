"""Agent auth: agent_id on decisions/sessions, and the audit_log table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    # Offline (--sql) mode has no live database to inspect.
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    # A pre-Alembic database may already have agent_id if create_all ran on the new models.
    for table in ("decisions", "sessions"):
        if not _has_column(table, "agent_id"):
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("agent_id", sa.String(36), nullable=True))

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), nullable=True),
        sa.Column("tool_name", sa.String(50), nullable=False),
        sa.Column("project_id", sa.String(500), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("duration_ms", sa.Integer),
    )
    op.create_index("ix_audit_log_agent_id_timestamp", "audit_log", ["agent_id", "timestamp"])
    op.create_index(
        "ix_audit_log_project_id_timestamp", "audit_log", ["project_id", "timestamp"]
    )
    op.create_index("ix_audit_log_user_id_timestamp", "audit_log", ["user_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_id_timestamp", table_name="audit_log")
    op.drop_index("ix_audit_log_project_id_timestamp", table_name="audit_log")
    op.drop_index("ix_audit_log_agent_id_timestamp", table_name="audit_log")
    op.drop_table("audit_log")
    for table in ("sessions", "decisions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("agent_id")
