"""Report clients that need an operator's review. Checks only report; they never change data."""
from django.core import checks
from django.db import DatabaseError

from clients import services

MAX_LISTED = 20


@checks.register(checks.Tags.database)
def orphaned_client_keys(app_configs, databases=None, **kwargs):
    # Database checks run on `migrate` and `check --database default`, not on every start.
    if not databases:
        return []
    try:
        orphans = services.orphaned_clients()
    except DatabaseError:
        return []  # tables not migrated yet
    if not orphans:
        return []
    listed = ", ".join(f"{c.id} ({c.name!r}, user {c.user_id})" for c in orphans[:MAX_LISTED])
    more = f" and {len(orphans) - MAX_LISTED} more" if len(orphans) > MAX_LISTED else ""
    return [checks.Warning(
        f"{len(orphans)} client(s) belong to no existing user, and their API keys still work: "
        f"{listed}{more}.",
        hint="Revoke each one in the admin (Clients) unless an agent still needs it.",
        id="clients.W001",
    )]


@checks.register(checks.Tags.database)
def shared_projects(app_configs, databases=None, **kwargs):
    """clients.W002: a project's clients belong to more than one user (ADR 031)."""
    if not databases:
        return []
    try:
        shared = services.shared_projects()
    except DatabaseError:
        return []  # tables not migrated yet
    if not shared:
        return []
    lines = [
        f"{project_id}: " + ", ".join(f"{c.id} ({c.name!r}, user {c.user_id})" for c in clients)
        for project_id, clients in list(shared.items())[:MAX_LISTED]
    ]
    more = f" and {len(shared) - MAX_LISTED} more" if len(shared) > MAX_LISTED else ""
    return [checks.Warning(
        f"{len(shared)} project(s) have clients belonging to more than one user: "
        + "; ".join(lines) + more + ".",
        hint="Review these projects and revoke the clients that don't belong to the project owner.",
        id="clients.W002",
    )]
