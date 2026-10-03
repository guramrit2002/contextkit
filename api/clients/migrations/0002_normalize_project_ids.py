"""
Normalize every client's project ID to its canonical form (ADR 030).

Uses a frozen copy of core.projects.normalize_project_id as of this migration, so later changes
to that function can never rewrite history. If two clients of one user collapse into the same
project, the migration stops and names them: deleting either could break an agent still using
its key, so the operator decides which one to revoke.
"""
import re
from typing import Optional
from urllib.parse import urlsplit

from django.db import migrations

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


# --- End of frozen copy. ---


def normalize_client_project_ids(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    clients = list(Client.objects.order_by("user_id", "created_at"))

    owners: dict[tuple[str, str], object] = {}
    collisions = []
    for client in clients:
        key = (client.user_id, normalize_project_id(client.project_id))
        if key in owners:
            first = owners[key]
            collisions.append(
                f"user {client.user_id}: {first.id} ({first.name!r}, {first.project_id!r}) and "
                f"{client.id} ({client.name!r}, {client.project_id!r}) are both {key[1]!r}"
            )
        else:
            owners[key] = client
    if collisions:
        raise RuntimeError(
            "Clients collapse into the same project after normalization. Revoke one of each "
            "pair, then rerun the migration:\n  " + "\n  ".join(collisions)
        )

    for (_, canonical), client in owners.items():
        if client.project_id != canonical:
            Client.objects.filter(pk=client.pk).update(project_id=canonical)


class Migration(migrations.Migration):
    dependencies = [("clients", "0001_initial")]

    operations = [
        # Reverse is a no-op: the original forms are not kept, and canonical IDs stay valid.
        migrations.RunPython(normalize_client_project_ids, migrations.RunPython.noop),
    ]
