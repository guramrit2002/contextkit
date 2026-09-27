import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from core import audit, auth, services, storage
from core.errors import AuthenticationError, AuthorizationError, StorageError
from core.models import Agent, ApiKey, DjangoOwnedBase


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "contextkit.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    storage.init_db()
    return path


@pytest.fixture()
def agent_tables(db_path):
    # Stand-in for Django's migration of agents/api_keys.
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    DjangoOwnedBase.metadata.create_all(engine)
    engine.dispose()
    return db_path


@pytest.fixture()
def make_agent(agent_tables):
    def _make(user_id="alice", project_id="proj-1", api_key="ck_alice_key"):
        session = storage.get_session()
        now = datetime.now(UTC)
        agent_id = f"agent-{user_id}-{project_id}"
        session.add(Agent(
            id=agent_id, user_id=user_id, project_id=project_id, name=user_id,
            created_at=now, updated_at=now,
        ))
        session.add(ApiKey(
            id=f"key-{agent_id}", agent_id=agent_id,
            key_hash=auth.hash_api_key(api_key), created_at=now,
        ))
        session.commit()
        session.close()
        return auth.AgentContext(agent_id, user_id, project_id), api_key

    return _make


def audit_rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY timestamp")]


def recorder():
    calls = []

    async def operation():
        calls.append(auth.current_agent())
        return "done"

    return calls, operation


# hash_api_key / authenticate_agent


def test_hash_api_key_is_sha256_hex_matching_django_issuer():
    assert auth.hash_api_key("ck_test") == (
        "942d317dc7797b98b262d88716422069144f262ddc1ea8bfe041c3a5ede7c27a"
    )


def test_authenticate_valid_key_returns_agent_context(make_agent):
    expected, key = make_agent()

    assert auth.authenticate_agent(key) == expected


def test_authenticate_strips_surrounding_whitespace(make_agent):
    expected, key = make_agent()

    assert auth.authenticate_agent(f"  {key}\n") == expected


def test_authenticate_unknown_key_is_rejected(make_agent):
    make_agent()

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        auth.authenticate_agent("ck_wrong")


@pytest.mark.parametrize("bad_key", [None, "", "   ", 123])
def test_authenticate_rejects_missing_or_malformed_key(bad_key, agent_tables):
    with pytest.raises(AuthenticationError, match="required"):
        auth.authenticate_agent(bad_key)


def test_authenticate_rejects_oversized_key_without_lookup(monkeypatch, agent_tables):
    monkeypatch.setattr(storage, "get_agent_by_key_hash", pytest.fail)

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        auth.authenticate_agent("k" * (auth.MAX_API_KEY_LENGTH + 1))


def test_missing_agent_tables_gives_actionable_error(db_path):
    with pytest.raises(StorageError, match="manage.py migrate"):
        auth.authenticate_agent("ck_anything")


def test_other_database_errors_are_not_masked(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE api_keys (id TEXT, agent_id TEXT, key_hash TEXT)")

    with pytest.raises(DBAPIError):
        auth.authenticate_agent("ck_anything")


# validate_agent_project_access


AGENT = auth.AgentContext("agent-1", "alice", "proj-1")


def test_omitted_project_resolves_to_assigned_project():
    assert auth.validate_agent_project_access(AGENT, None) == "proj-1"


def test_matching_project_is_allowed():
    assert auth.validate_agent_project_access(AGENT, "proj-1") == "proj-1"


def test_other_project_is_denied():
    with pytest.raises(AuthorizationError, match="proj-2"):
        auth.validate_agent_project_access(AGENT, "proj-2")


def test_authorization_error_is_a_permission_error():
    assert issubclass(AuthorizationError, PermissionError)


# guarded_call


@pytest.mark.asyncio
async def test_local_mode_without_key_runs_unauthenticated_and_unaudited(db_path):
    calls, operation = recorder()

    assert await auth.guarded_call("get_context", None, "proj-1", operation) == "done"
    assert calls == [None]
    assert audit_rows(db_path) == []


@pytest.mark.asyncio
async def test_require_auth_denies_call_without_key(db_path, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    calls, operation = recorder()

    with pytest.raises(AuthenticationError, match="required"):
        await auth.guarded_call("get_context", None, "proj-1", operation)

    assert calls == []
    [row] = audit_rows(db_path)
    assert (row["status"], row["agent_id"], row["project_id"]) == ("denied", None, "proj-1")


@pytest.mark.asyncio
async def test_invalid_key_is_denied_and_audited(make_agent):
    make_agent()
    calls, operation = recorder()

    with pytest.raises(AuthenticationError):
        await auth.guarded_call("log_decision", "ck_wrong", "proj-1", operation)

    assert calls == []
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "denied"
    assert row["agent_id"] is None
    assert row["tool_name"] == "log_decision"
    assert row["error_message"] == "Invalid API key"


@pytest.mark.asyncio
async def test_key_is_verified_even_when_auth_not_required(make_agent):
    make_agent()
    _, operation = recorder()

    with pytest.raises(AuthenticationError):
        await auth.guarded_call("get_context", "ck_wrong", None, operation)


@pytest.mark.asyncio
async def test_project_mismatch_is_denied_and_audited(make_agent):
    agent, key = make_agent()
    calls, operation = recorder()

    with pytest.raises(AuthorizationError):
        await auth.guarded_call("get_context", key, "proj-2", operation)

    assert calls == []
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "denied"
    assert (row["agent_id"], row["user_id"], row["project_id"]) == (
        agent.agent_id, "alice", "proj-2",
    )


@pytest.mark.asyncio
async def test_success_runs_as_agent_and_is_audited(make_agent):
    agent, key = make_agent()
    calls, operation = recorder()

    assert await auth.guarded_call("get_context", key, None, operation) == "done"

    assert calls == [agent]
    assert auth.current_agent() is None
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "success"
    assert (row["agent_id"], row["user_id"], row["project_id"]) == (
        agent.agent_id, "alice", "proj-1",
    )
    assert row["duration_ms"] >= 0
    assert row["error_message"] is None


@pytest.mark.asyncio
async def test_operation_error_is_audited_with_redacted_message(make_agent):
    _, key = make_agent()

    async def failing():
        raise ValueError("could not connect with password=hunter2")

    with pytest.raises(ValueError):
        await auth.guarded_call("update_state", key, "proj-1", failing)

    assert auth.current_agent() is None
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "error"
    assert "hunter2" not in row["error_message"]
    assert row["error_message"].startswith("ValueError:")


@pytest.mark.asyncio
async def test_audit_write_failure_does_not_fail_the_call(make_agent, monkeypatch):
    _, key = make_agent()
    _, operation = recorder()

    def broken(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(storage, "create_audit_log_entry", broken)

    assert await auth.guarded_call("get_context", key, None, operation) == "done"


def test_authenticate_request_requiring_key_denies_keyless_call(db_path):
    with pytest.raises(AuthenticationError, match="required"):
        auth.authenticate_request("get_context", None, "proj-1", key_required=True)

    [row] = audit_rows(db_path)
    assert (row["status"], row["agent_id"]) == ("denied", None)


def test_authenticate_request_without_requirement_returns_none_for_keyless_call(db_path):
    assert auth.authenticate_request("get_context", None, None, key_required=False) is None
    assert audit_rows(db_path) == []


@pytest.mark.asyncio
async def test_run_as_agent_uses_already_authenticated_agent(make_agent, monkeypatch):
    agent, _ = make_agent()
    monkeypatch.setattr(storage, "get_agent_by_key_hash", pytest.fail)
    calls, operation = recorder()

    assert await auth.run_as_agent("get_context", agent, None, operation) == "done"

    assert calls == [agent]
    [row] = audit_rows(storage.get_db_path())
    assert (row["status"], row["project_id"]) == ("success", "proj-1")


# audit


def test_unknown_audit_status_is_rejected():
    with pytest.raises(ValueError, match="Unknown audit status"):
        audit.log_audit_event("get_context", "ok")


def test_long_error_messages_are_truncated(db_path):
    audit.log_audit_event("get_context", "error", error_message="x" * 5000)

    [row] = audit_rows(db_path)
    assert len(row["error_message"]) == audit.MAX_ERROR_LENGTH


# services running as an agent


@pytest.mark.asyncio
async def test_writes_record_agent_user_and_assigned_project(make_agent):
    agent, key = make_agent()

    async def work():
        decision = await services.log_decision(None, "Use Alembic", "Schema versioning")
        session = await services.log_session(None, "Added migrations")
        state = await services.update_state(None, "Auth core done", "MCP decorator")
        return decision, session, state

    decision, session, state = await auth.guarded_call("log_decision", key, None, work)

    assert (decision["project_id"], decision["agent_id"], decision["user_id"]) == (
        "proj-1", agent.agent_id, "alice",
    )
    assert (session["project_id"], session["agent_id"], session["user_id"]) == (
        "proj-1", agent.agent_id, "alice",
    )
    assert state["project_id"] == "proj-1"
    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT user_id FROM state").fetchone() == ("alice",)


@pytest.mark.asyncio
async def test_briefing_shows_which_agent_wrote_each_record(make_agent):
    agent, key = make_agent()

    async def work():
        await services.log_decision(None, "Use Alembic", "Schema versioning")
        await services.log_session(None, "Added migrations")
        return await services.get_briefing()

    briefing = await auth.guarded_call("get_context", key, None, work)

    assert briefing["project"]["id"] == "proj-1"
    assert briefing["decisions"][0]["agent_id"] == agent.agent_id
    assert briefing["recent_sessions"][0]["agent_id"] == agent.agent_id


@pytest.mark.asyncio
async def test_export_markdown_uses_assigned_project(make_agent):
    _, key = make_agent()

    markdown = await auth.guarded_call("export_markdown", key, None, services.export_markdown)

    assert "`proj-1`" in markdown


@pytest.mark.asyncio
async def test_services_reject_other_project_even_inside_guarded_call(make_agent):
    _, key = make_agent()

    async def sneaky():
        return await services.log_decision("proj-2", "Escalate", "Try another project")

    with pytest.raises(AuthorizationError):
        await auth.guarded_call("log_decision", key, None, sneaky)

    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "error"
    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone() == (0,)


@pytest.mark.asyncio
async def test_state_owner_is_updated_on_later_write(make_agent):
    await services.update_state("proj-1", "Started locally", "Continue")
    _, key = make_agent()

    async def work():
        return await services.update_state(None, "Continued as agent", "Ship")

    await auth.guarded_call("update_state", key, None, work)

    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT user_id, progress FROM state").fetchall() == [
            ("alice", "Continued as agent")
        ]


@pytest.mark.asyncio
async def test_local_mode_writes_keep_default_user_and_no_agent(db_path):
    decision = await services.log_decision("proj-1", "Local", "No agent")

    assert decision["agent_id"] is None
    assert decision["user_id"]
