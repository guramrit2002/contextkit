"""Startup checks for the local GitHub stand-in (accounts.mock_github)."""
from django.conf import settings
from django.core import checks
from django.db import connection

from accounts import mock_github


def github_mock(app_configs, **kwargs):
    if not mock_github.requested():
        return []
    if connection.vendor != "sqlite":
        # The mock approves any repository ownership; on the shared database that would let a
        # local run register other people's repositories (ADR 031).
        return [checks.Error(
            "GITHUB_MOCK is on, but the database isn't SQLite.",
            hint="The GitHub mock is for local SQLite only. Unset GITHUB_MOCK, or run with "
                 "DATABASE_URL empty and CONTEXTKIT_ALLOW_SQLITE=true.",
            id="accounts.E001",
        )]
    if not settings.DEBUG:
        return [checks.Warning(
            "GITHUB_MOCK is ignored because DEBUG is off; real GitHub is used.",
            hint="Set DJANGO_DEBUG=true for local development with the mock.",
            id="accounts.W001",
        )]
    return [checks.Info(
        f"GitHub is mocked: signed in as {mock_github.login()!r}, owning "
        f"{', '.join(mock_github.repo_names())}.",
        id="accounts.I001",
    )]
