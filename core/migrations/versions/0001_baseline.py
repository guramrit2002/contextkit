"""Baseline: core context tables as created before Alembic was introduced.

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(500), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("git_remote", sa.String(500)),
        sa.Column("local_path", sa.String(500)),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(500), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("alternatives_considered", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(500),
            sa.ForeignKey("projects.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("progress", sa.Text, nullable=False),
        sa.Column("next_steps", sa.Text, nullable=False),
        sa.Column("blockers", sa.Text),
        sa.Column("updated_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(500), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("decisions_made", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("state")
    op.drop_table("decisions")
    op.drop_table("projects")
