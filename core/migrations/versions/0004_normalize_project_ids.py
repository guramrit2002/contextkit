"""Normalize project IDs to their canonical form, merging variants of one project (ADR 030).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02

Uses a frozen copy of core.projects as of this migration, so later changes to it can never
rewrite history. Merges cannot be undone, so downgrade is a no-op.
"""
import logging
import os
import re
from typing import Optional
from urllib.parse import urlsplit

import sqlalchemy as sa
from alembic import context, op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# --- Frozen copy of core.projects (2026-10-02). Do not edit. ---
MAX_PROJECT_ID_LENGTH = 500

REMOTE_SCHEMES = ("https", "http", "ssh", "git")
# Hosts that treat owner and repository names case-insensitively.
CASE_INSENSITIVE_HOSTS = ("github.com",)

# scp-style remote, `[user@]host:path` (git@github.com:owner/repo.git). Without a user, the
# host must contain a dot, so a Windows path like C:\app is not mistaken for a remote.
_SCP_REMOTE = re.compile(r"^(?:(?P<user>[^@/\s:]+)@)?(?P<host>[^@/\s:]+):(?P<path>\S.*)$")
# Schemeless `host/path` (github.com/owner/repo), where the host contains a dot.
_BARE_REMOTE = re.compile(r"^(?P<host>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)/(?P<path>.+)$")


def _parse_remote(value: str) -> Optional[tuple[str, str]]:
    """Split a git remote into (host, path), or None if the value is not a remote."""
    if "://" in value:
        parts = urlsplit(value)
        # hostname drops credentials and the port, and lowercases the host.
        if parts.scheme.lower() not in REMOTE_SCHEMES or not parts.hostname:
            return None
        return parts.hostname, parts.path

    scp = _SCP_REMOTE.match(value)
    if scp and (scp["user"] or "." in scp["host"]):
        return scp["host"].lower(), scp["path"]

    bare = _BARE_REMOTE.match(value)
    if bare:
        return bare["host"].lower(), bare["path"]
    return None


def _clean_path(path: str) -> str:
    # Loop so that removing ".git" or "/" never exposes another one: keeps this idempotent.
    path = path.strip("/")
    while path.endswith(".git") or path.endswith("/"):
        path = path.removesuffix(".git").rstrip("/")
    return path


def normalize_project_id(raw: str) -> str:
    """
    Return the canonical project ID.

    Git remotes become `https://<host>/<path>`, without credentials, port, `.git` or trailing
    slashes; the host is lowercased, and so is the whole path for GitHub. Anything else (a
    folder path) is only trimmed of whitespace and trailing slashes.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Project ID cannot be empty")

    value = raw.strip()
    remote = _parse_remote(value)
    path = _clean_path(remote[1]) if remote else ""
    if remote and path:
        host = remote[0]
        if host in CASE_INSENSITIVE_HOSTS:
            path = path.lower()
        canonical = f"https://{host}/{path}"
    else:
        canonical = value.rstrip("/") or "/"

    if len(canonical) > MAX_PROJECT_ID_LENGTH:
        raise ValueError(f"Project ID is too long (max {MAX_PROJECT_ID_LENGTH} characters)")
    return canonical


def normalize_or_keep(raw: Optional[str]) -> Optional[str]:
    """The canonical ID when there is one; otherwise the value as given (for audit records)."""
    try:
        return normalize_project_id(raw) if raw else raw
    except ValueError:
        return raw


# --- End of frozen copy. ---


def _move_children(conn, old: str, new: str) -> None:
    for table in ("decisions", "sessions"):
        conn.execute(
            sa.text(f"UPDATE {table} SET project_id = :new WHERE project_id = :old"),
            {"new": new, "old": old},
        )


def _merge_state(conn, old: str, new: str) -> None:
    """state allows one row per project: keep the most recently updated one."""
    rows = conn.execute(
        sa.text("SELECT id, project_id, updated_at FROM state WHERE project_id IN (:old, :new)"),
        {"old": old, "new": new},
    ).mappings().all()
    if not rows:
        return
    newest = max(rows, key=lambda r: (r["updated_at"] is not None, r["updated_at"] or ""))
    for row in rows:
        if row["id"] != newest["id"]:
            conn.execute(sa.text("DELETE FROM state WHERE id = :id"), {"id": row["id"]})
    if newest["project_id"] != new:
        conn.execute(
            sa.text("UPDATE state SET project_id = :new WHERE id = :id"),
            {"new": new, "id": newest["id"]},
        )


def upgrade() -> None:
    if context.is_offline_mode():
        # Merging depends on the rows present, which --sql output cannot know.
        logger.warning("0004 normalizes data and is skipped in offline (--sql) mode.")
        return

    conn = op.get_bind()
    projects = conn.execute(
        sa.text(
            "SELECT id, git_remote, local_path, user_id, created_at, updated_at "
            "FROM projects ORDER BY created_at"
        )
    ).mappings().all()
    existing = {p["id"] for p in projects}

    for project in projects:
        old = project["id"]
        canonical = normalize_or_keep(old)
        remote = normalize_or_keep(project["git_remote"])

        if canonical == old:
            if remote != project["git_remote"]:
                conn.execute(
                    sa.text("UPDATE projects SET git_remote = :remote WHERE id = :id"),
                    {"remote": remote, "id": old},
                )
            continue

        if canonical in existing:
            logger.info("Merging project %r into %r", old, canonical)
        else:
            logger.info("Renaming project %r to %r", old, canonical)
            conn.execute(
                sa.text(
                    "INSERT INTO projects (id, name, git_remote, local_path, user_id, created_at, "
                    "updated_at) VALUES (:id, :name, :git_remote, :local_path, :user_id, "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": canonical,
                    "name": os.path.basename(canonical),
                    "git_remote": remote,
                    "local_path": project["local_path"],
                    "user_id": project["user_id"],
                    "created_at": project["created_at"],
                    "updated_at": project["updated_at"],
                },
            )
            existing.add(canonical)

        _move_children(conn, old, canonical)
        _merge_state(conn, old, canonical)
        conn.execute(sa.text("DELETE FROM projects WHERE id = :id"), {"id": old})
        existing.discard(old)

    audited = conn.execute(
        sa.text("SELECT DISTINCT project_id FROM audit_log WHERE project_id IS NOT NULL")
    ).scalars().all()
    for project_id in audited:
        canonical = normalize_or_keep(project_id)
        if canonical != project_id:
            conn.execute(
                sa.text("UPDATE audit_log SET project_id = :new WHERE project_id = :old"),
                {"new": canonical, "old": project_id},
            )


def downgrade() -> None:
    # No-op: merged projects cannot be split again, and canonical IDs stay valid for 0003.
    pass
