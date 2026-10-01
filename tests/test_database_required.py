"""ADR 029: contextkit runs only against DATABASE_URL; SQLite is an explicit test-only opt-in."""
import os
import subprocess
import sys

import pytest

from core.config import (
    REPO_ROOT,
    resolve_database_url,
    resolve_django_database_url,
    sqlite_allowed,
)
from core.errors import ConfigurationError

PG_URL = "postgresql://postgres.ref:secret@aws-0-ap.pooler.supabase.com:5432/postgres"


@pytest.fixture()
def production_env(monkeypatch):
    """No DATABASE_URL and no SQLite opt-in: what a misconfigured server sees."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CONTEXTKIT_ALLOW_SQLITE", "false")


@pytest.mark.parametrize("resolve", [resolve_database_url, resolve_django_database_url])
def test_missing_database_url_is_a_configuration_error(production_env, resolve):
    with pytest.raises(ConfigurationError, match="DATABASE_URL is not set"):
        resolve()


@pytest.mark.parametrize("resolve", [resolve_database_url, resolve_django_database_url])
def test_database_url_is_used_whether_or_not_sqlite_is_allowed(monkeypatch, resolve):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    for allowed in ("true", "false"):
        monkeypatch.setenv("CONTEXTKIT_ALLOW_SQLITE", allowed)
        assert resolve().startswith("postgresql+psycopg://")


def test_tests_opt_in_to_sqlite():
    assert sqlite_allowed()
    assert resolve_database_url().startswith("sqlite:///")


def test_error_message_never_contains_a_database_url(production_env):
    with pytest.raises(ConfigurationError) as raised:
        resolve_database_url()
    assert "://" not in str(raised.value)


def _start_server_without_database():
    env = {k: v for k, v in os.environ.items() if k != "CONTEXTKIT_ALLOW_SQLITE"}
    # Present but empty, so a developer's .env can't fill it in (dotenv never overrides).
    env["DATABASE_URL"] = ""
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_mcp_server_refuses_to_start_without_database_url():
    result = _start_server_without_database()

    assert result.returncode != 0
    assert "ConfigurationError" in result.stderr
    assert "DATABASE_URL is not set" in result.stderr
