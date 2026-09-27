import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from core import auth, storage
from core.models import Agent, ApiKey, DjangoOwnedBase
from mcp_server import auth_middleware, tools
from mcp_server.server import mcp, setup_tools

KEY = "ck_agent_key"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "contextkit.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("CONTEXTKIT_API_KEY", raising=False)
    storage.init_db()
    engine = create_engine(f"sqlite:///{path}", poolclass=NullPool)
    DjangoOwnedBase.metadata.create_all(engine)
    engine.dispose()

    session = storage.get_session()
    now = datetime.now(UTC)
    session.add(Agent(
        id="agent-1", user_id="alice", project_id="proj-1", name="builder",
        created_at=now, updated_at=now,
    ))
    session.add(ApiKey(
        id="key-1", agent_id="agent-1", key_hash=auth.hash_api_key(KEY), created_at=now,
    ))
    session.commit()
    session.close()
    setup_tools()
    return path


@pytest.fixture()
def http_headers(monkeypatch):
    """Simulate an HTTP request carrying the given headers."""

    def _set(headers):
        request = SimpleNamespace(headers=headers)
        monkeypatch.setattr(auth_middleware, "get_http_request", lambda: request)

    return _set


def audit_rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT tool_name, status, agent_id, project_id FROM audit_log ORDER BY timestamp"
        ).fetchall()


def decision_rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT project_id, agent_id, user_id FROM decisions").fetchall()


LOG_DECISION = {"input": {"decision": "Use Alembic", "reasoning": "Versioned schema"}}


# stdio: key from CONTEXTKIT_API_KEY


@pytest.mark.asyncio
async def test_stdio_key_from_environment_authenticates_and_audits(db, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)

    result = await mcp.call_tool("log_decision", LOG_DECISION)

    assert result.structured_content["success"] is True
    assert decision_rows(db) == [("proj-1", "agent-1", "alice")]
    assert audit_rows(db) == [("log_decision", "success", "agent-1", "proj-1")]


@pytest.mark.asyncio
async def test_stdio_invalid_key_is_denied(db, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", "ck_wrong")

    with pytest.raises(ToolError, match="Invalid API key"):
        await mcp.call_tool("log_decision", LOG_DECISION)

    assert decision_rows(db) == []
    assert audit_rows(db) == [("log_decision", "denied", None, None)]


@pytest.mark.asyncio
async def test_stdio_without_key_runs_in_local_mode(db):
    result = await mcp.call_tool("get_context", {"project_id": "local-project"})

    assert result.structured_content["project"]["id"] == "local-project"
    assert audit_rows(db) == []


@pytest.mark.asyncio
async def test_require_auth_rejects_calls_without_key(db, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    with pytest.raises(ToolError, match="API key is required"):
        await mcp.call_tool("get_context", {"project_id": "proj-1"})

    assert audit_rows(db) == [("get_context", "denied", None, "proj-1")]


@pytest.mark.asyncio
async def test_other_project_is_denied_for_every_tool(db, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)
    calls = {
        "get_context": {"project_id": "proj-2"},
        "log_decision": {"input": {**LOG_DECISION["input"], "project_id": "proj-2"}},
        "update_state": {"input": {"progress": "p", "next_steps": "n", "project_id": "proj-2"}},
        "log_session": {"input": {"summary": "s", "project_id": "proj-2"}},
        "export_markdown": {"project_id": "proj-2"},
    }

    for tool_name, arguments in calls.items():
        with pytest.raises(ToolError, match="not authorized for project proj-2"):
            await mcp.call_tool(tool_name, arguments)

    assert audit_rows(db) == [(name, "denied", "agent-1", "proj-2") for name in calls]


@pytest.mark.asyncio
async def test_all_tools_work_for_assigned_project(db, monkeypatch, tmp_path):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)
    output = tmp_path / "context.md"

    await mcp.call_tool("log_decision", LOG_DECISION)
    await mcp.call_tool("update_state", {"input": {"progress": "p", "next_steps": "n"}})
    await mcp.call_tool("log_session", {"input": {"summary": "Wired MCP auth"}})
    context = await mcp.call_tool("get_context", {})
    await mcp.call_tool("export_markdown", {"output_path": str(output)})

    briefing = context.structured_content
    assert briefing["project"]["id"] == "proj-1"
    assert briefing["recent_sessions"][0]["agent_id"] == "agent-1"
    assert "`proj-1`" in output.read_text()
    assert [row[:2] for row in audit_rows(db)] == [
        ("log_decision", "success"),
        ("update_state", "success"),
        ("log_session", "success"),
        ("get_context", "success"),
        ("export_markdown", "success"),
    ]


@pytest.mark.asyncio
async def test_tool_failure_is_audited_as_error(db, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)

    with pytest.raises(ToolError):
        await mcp.call_tool("log_decision", {"input": {"decision": "  ", "reasoning": "r"}})

    assert audit_rows(db) == [("log_decision", "error", "agent-1", "proj-1")]


# HTTP: key only from the Authorization header


@pytest.mark.asyncio
async def test_http_bearer_header_authenticates(db, http_headers):
    http_headers({"Authorization": f"Bearer {KEY}"})

    await mcp.call_tool("log_decision", LOG_DECISION)

    assert decision_rows(db) == [("proj-1", "agent-1", "alice")]


@pytest.mark.asyncio
async def test_http_ignores_server_environment_key(db, http_headers, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    http_headers({})

    with pytest.raises(ToolError, match="API key is required"):
        await mcp.call_tool("get_context", {})

    assert audit_rows(db) == [("get_context", "denied", None, None)]


@pytest.mark.asyncio
async def test_http_malformed_authorization_header_is_denied(db, http_headers):
    http_headers({"Authorization": f"Basic {KEY}"})

    with pytest.raises(ToolError, match="Invalid API key"):
        await mcp.call_tool("get_context", {})


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer ck_abc", "ck_abc"),
        ("bearer   ck_abc  ", "ck_abc"),
        ("Basic xyz", "Basic xyz"),
        ("Bearer", "Bearer"),
        ("", None),
    ],
)
def test_resolve_api_key_parses_authorization_header(http_headers, header, expected):
    http_headers({"authorization": header} if header else {})

    assert auth_middleware.resolve_api_key() == expected


def test_resolve_api_key_over_stdio_reads_environment(monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", "ck_env")
    assert auth_middleware.resolve_api_key() == "ck_env"

    monkeypatch.setenv("CONTEXTKIT_API_KEY", "")
    assert auth_middleware.resolve_api_key() is None


# The decorator must not change what agents see


@pytest.mark.asyncio
async def test_tool_schemas_are_unchanged_by_auth_decorator(db):
    schemas = {tool.name: tool.parameters for tool in await mcp.list_tools()}

    assert set(schemas["get_context"]["properties"]) == {"project_id"}
    assert set(schemas["log_decision"]["properties"]) == {"input"}
    assert set(schemas["export_markdown"]["properties"]) == {
        "input", "project_id", "output_path",
    }


@pytest.mark.asyncio
async def test_direct_calls_pass_project_from_input_model(db, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_API_KEY", KEY)

    with pytest.raises(auth.AuthorizationError):
        await tools.get_context(tools.GetContextInput(project_id="proj-2"))

    result = await tools.get_context(tools.GetContextInput())
    assert result["project"]["id"] == "proj-1"
