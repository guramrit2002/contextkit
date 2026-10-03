"""Hosted deployment (ADR 026): database URLs, engines, entrypoint, and hosted-only rules."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from alembic import command
from fastmcp.exceptions import ToolError
from sqlalchemy.pool import NullPool, QueuePool

from core import storage
from core.config import (
    config,
    is_sqlite,
    resolve_database_url,
    resolve_db_path,
    resolve_django_database_url,
    resolve_django_db_path,
)
from core.errors import ValidationError
from mcp_server import auth_middleware

PG_URL = "postgresql://postgres.ref:secret@aws-0-ap.pooler.supabase.com:5432/postgres"
PG_SQLALCHEMY = PG_URL.replace("postgresql://", "postgresql+psycopg://", 1)
TOOLS = {"get_context", "log_decision", "update_state", "log_session", "export_markdown"}


@pytest.fixture(autouse=True)
def fresh_engine_cache(monkeypatch):
    monkeypatch.setattr(storage, "_engines", {})
    monkeypatch.setattr(storage, "_sessionmakers", {})


@pytest.fixture()
def core_db(tmp_path, monkeypatch):
    path = tmp_path / "core.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    return path


@pytest.fixture()
def hosted(monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_HOSTED", "true")


# URL resolution


def test_without_database_url_core_and_django_use_their_sqlite_files():
    assert resolve_database_url() == f"sqlite:///{resolve_db_path()}"
    assert resolve_django_database_url() == f"sqlite:///{resolve_django_db_path()}"
    assert resolve_database_url() != resolve_django_database_url()


def test_database_url_is_one_postgres_database_for_both(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL + "?sslmode=require")

    assert resolve_database_url() == PG_SQLALCHEMY + "?sslmode=require"
    assert resolve_django_database_url() == resolve_database_url()


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_postgres_schemes_are_normalized_to_psycopg(monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", scheme + "u:p@h:5432/db")

    assert resolve_database_url() == "postgresql+psycopg://u:p@h:5432/db"


def test_explicit_driver_is_kept(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")

    assert resolve_database_url() == "postgresql+psycopg://u:p@h/db"


def test_blank_database_url_means_local_mode(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")

    assert is_sqlite(resolve_database_url())


# Engines


def test_sqlite_engine_uses_null_pool(core_db):
    assert isinstance(storage.get_engine().pool, NullPool)


def test_postgres_engine_uses_a_small_pre_pinged_pool(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)

    engine = storage.get_engine()

    assert isinstance(engine.pool, QueuePool)
    assert engine.pool._pre_ping is True
    assert (engine.pool.size(), engine.pool._max_overflow) == (5, 5)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_engine_and_sessionmaker_are_cached_per_url(core_db, monkeypatch, tmp_path):
    first = storage.get_engine()
    assert storage.get_engine() is first
    storage.get_session().close()
    assert storage._sessionmakers[resolve_database_url()].kw["bind"] is first

    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(tmp_path / "other.sqlite3"))
    assert storage.get_engine() is not first


def test_django_tables_share_the_core_engine_on_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)

    assert storage.get_django_engine() is storage.get_engine()


def test_django_tables_use_a_separate_read_only_engine_on_sqlite(core_db):
    engine = storage.get_django_engine()
    try:
        assert engine is not storage.get_engine()
        assert "mode=ro" in str(engine.url)
    finally:
        engine.dispose()


def test_alembic_config_survives_url_encoded_passwords(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p%40ss%23@h:5432/db")

    url = storage._alembic_config().get_main_option("sqlalchemy.url")

    assert url == "postgresql+psycopg://u:p%40ss%23@h:5432/db"


# Read-only key lookup


class RecordingSession:
    def __init__(self, bind):
        self.bind = bind
        self.statements = []
        RecordingSession.last = self

    def execute(self, statement):
        self.statements.append(str(statement))
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def rollback(self):
        pass

    def close(self):
        pass


def test_postgres_key_lookup_runs_read_only_before_the_query(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.setattr(storage, "Session", RecordingSession)

    assert storage.get_client_by_key_hash("abc") is None

    first, lookup = RecordingSession.last.statements
    assert first == "SET TRANSACTION READ ONLY"
    assert "FROM clients JOIN api_keys" in lookup
    assert RecordingSession.last.bind is storage.get_engine()


def test_sqlite_key_lookup_relies_on_mode_ro_instead(core_db, monkeypatch):
    monkeypatch.setattr(storage, "Session", RecordingSession)

    storage.get_client_by_key_hash("abc")

    assert all("SET TRANSACTION" not in s for s in RecordingSession.last.statements)


def test_missing_tables_error_never_includes_the_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)

    assert "secret" not in storage._django_database_label()
    assert storage._django_database_label() == "the DATABASE_URL database"


# Entrypoint


def list_tool_names(server):
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_root_entrypoint_exposes_the_five_tools_and_instructions():
    import server
    from mcp_server import server as package_server

    assert server.mcp is package_server.mcp
    assert list_tool_names(server.mcp) == TOOLS
    assert "get_context" in server.mcp.instructions
    assert "log_session" in server.mcp.instructions


def test_registering_twice_does_not_duplicate_tools():
    from mcp_server.server import mcp, setup_tools

    setup_tools()
    setup_tools()

    assert list_tool_names(mcp) == TOOLS


# Hosted mode


def test_hosted_always_requires_auth(hosted, monkeypatch):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    assert config.auth_required()

    monkeypatch.setenv("REQUIRE_AUTH", "false")
    assert config.auth_required()


def test_local_mode_keeps_require_auth_switch(monkeypatch):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    assert not config.auth_required()


def test_hosted_never_detects_the_servers_own_project(hosted):
    with mock.patch.object(storage.subprocess, "check_output") as git:
        with pytest.raises(ValidationError, match="project_id is required"):
            storage.detect_project_id()

    git.assert_not_called()


@pytest.mark.parametrize(
    ("project_id", "git_remote"),
    [
        ("https://github.com/acme/app", "https://github.com/acme/app"),
        ("git@github.com:acme/app.git", "git@github.com:acme/app.git"),
        ("ssh://git@host/acme/app", "ssh://git@host/acme/app"),
        ("my-project", None),
    ],
)
def test_hosted_projects_never_record_server_git_or_paths(
    hosted, core_db, project_id, git_remote
):
    storage.init_db()
    session = storage.get_session()
    try:
        with mock.patch.object(storage.subprocess, "check_output") as git:
            project = storage.get_or_create_project(project_id, session)
        git.assert_not_called()
        assert (project.git_remote, project.local_path) == (git_remote, None)
        assert project.name == Path(project_id).name
    finally:
        session.close()


def test_local_projects_still_record_git_remote_and_path(core_db):
    storage.init_db()
    session = storage.get_session()
    try:
        with mock.patch.object(
            storage.subprocess, "check_output", return_value="git@github.com:Owner/Repo.git\n"
        ):
            project = storage.get_or_create_project("local-proj", session)
        # Recorded in canonical form, never as the raw scp-style remote (ADR 030).
        assert project.git_remote == "https://github.com/owner/repo"
        assert project.local_path
    finally:
        session.close()


def test_hosted_keyless_mcp_call_is_denied(hosted, core_db):
    from mcp_server.server import mcp

    storage.init_db()
    with pytest.raises(ToolError, match="API key is required"):
        asyncio.run(mcp.call_tool("get_context", {"project_id": "proj-1"}))


def test_hosted_start_refuses_a_database_behind_the_code(hosted, core_db):
    from mcp_server.server import check_hosted_schema

    command.upgrade(storage._alembic_config(), "0002")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        check_hosted_schema()


def test_hosted_start_accepts_an_up_to_date_database(hosted, core_db):
    from mcp_server.server import check_hosted_schema

    storage.init_db()

    check_hosted_schema()


def test_local_start_skips_the_schema_check(core_db):
    from mcp_server import server

    with mock.patch.object(server, "core_schema_status", side_effect=AssertionError):
        server.check_hosted_schema()


# Export over HTTP


def test_export_with_output_path_over_http_is_rejected_and_writes_nothing(
    core_db, tmp_path, monkeypatch
):
    from mcp_server.server import mcp

    storage.init_db()
    monkeypatch.setattr(
        auth_middleware, "get_http_request", lambda: SimpleNamespace(headers={})
    )
    output = tmp_path / "context.md"

    with pytest.raises(ToolError, match="not supported over HTTP"):
        asyncio.run(mcp.call_tool(
            "export_markdown", {"project_id": "proj-1", "output_path": str(output)}
        ))

    assert not output.exists()


def test_export_over_http_without_output_path_returns_markdown(core_db, monkeypatch):
    from mcp_server.server import mcp

    storage.init_db()
    monkeypatch.setattr(
        auth_middleware, "get_http_request", lambda: SimpleNamespace(headers={})
    )

    result = asyncio.run(mcp.call_tool("export_markdown", {"project_id": "proj-1"}))

    assert "# Project Context" in result.structured_content["markdown"]


def test_is_http_request(monkeypatch):
    assert auth_middleware.is_http_request() is False

    monkeypatch.setattr(
        auth_middleware, "get_http_request", lambda: SimpleNamespace(headers={"a": "b"})
    )
    assert auth_middleware.is_http_request() is True
