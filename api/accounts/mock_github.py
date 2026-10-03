"""
A stand-in for GitHub for local development only (GITHUB_MOCK=true).

Every GitHub call (sign-in, the repository list, the ownership check) is answered locally, so
the Get key flow works without a GitHub OAuth app or network. Because the mock says "yes" to
ownership, it only switches on when DEBUG is on **and** the database is SQLite: pointed at the
shared Postgres database it could register other people's repositories (ADR 031), so it refuses.

Settings (all optional):
- GITHUB_MOCK_LOGIN: the signed-in GitHub login (default "mock-user")
- GITHUB_MOCK_ID: its numeric GitHub id (default 1000001)
- GITHUB_MOCK_REPOS: comma-separated repository names it owns (default "contextkit,demo-app")
"""
import os

from django.conf import settings
from django.db import connection

DEFAULT_LOGIN = "mock-user"
DEFAULT_ID = 1000001
DEFAULT_REPOS = "contextkit,demo-app"


def requested() -> bool:
    return os.getenv("GITHUB_MOCK", "").strip().lower() == "true"


def enabled() -> bool:
    """On only when asked for, in DEBUG, on SQLite. Never on the shared Postgres database."""
    return requested() and settings.DEBUG and connection.vendor == "sqlite"


def login() -> str:
    return os.getenv("GITHUB_MOCK_LOGIN", "").strip() or DEFAULT_LOGIN


def github_id() -> int:
    try:
        return int(os.getenv("GITHUB_MOCK_ID", DEFAULT_ID))
    except ValueError:
        return DEFAULT_ID


def repo_names() -> list[str]:
    raw = os.getenv("GITHUB_MOCK_REPOS", DEFAULT_REPOS)
    return [name.strip() for name in raw.split(",") if name.strip()]
