"""Report clients whose user no longer exists: their keys still work until revoked."""
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
