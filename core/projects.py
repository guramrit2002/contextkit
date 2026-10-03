"""Canonical project IDs (ADR 012, ADR 030).

Every form of a repository URL maps to one ID, so the URL a user types when creating a key
matches what their agent sends. Plain Python: core and Django both call this one function.
"""
import re
from typing import Optional
from urllib.parse import urlsplit

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
