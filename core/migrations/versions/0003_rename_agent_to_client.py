"""Rename the API key identity from agent to client (ADR 025).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ("decisions", "sessions", "audit_log")


def _rename(old: str, new: str) -> None:
    # Native RENAME COLUMN (SQLite 3.25+, Postgres): no table rebuild, and works in --sql mode.
    op.drop_index(f"ix_audit_log_{old}_timestamp", table_name="audit_log")
    for table in TABLES:
        op.alter_column(
            table, old, new_column_name=new, existing_type=sa.String(36), existing_nullable=True
        )
    op.create_index(f"ix_audit_log_{new}_timestamp", "audit_log", [new, "timestamp"])


def upgrade() -> None:
    _rename("agent_id", "client_id")


def downgrade() -> None:
    _rename("client_id", "agent_id")
