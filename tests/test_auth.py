import sqlite3

import pytest
from sqlalchemy.exc import DBAPIError

from core import audit, auth, services, storage
from core.errors import AuthenticationError, AuthorizationError, StorageError


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "contextkit.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    storage.init_db()
    return path


@pytest.fixture()
def client_tables(db_path, add_client):
    return db_path


@pytest.fixture()
def make_client(db_path, add_client):
    return add_client


def audit_rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY timestamp")]


def recorder():
    calls = []

    async def operation():
        calls.append(auth.current_client())
        return "done"

    return calls, operation


# hash_api_key / authenticate_client


def test_hash_api_key_is_sha256_hex_matching_django_issuer():
    assert auth.hash_api_key("ck_test") == (
        "942d317dc7797b98b262d88716422069144f262ddc1ea8bfe041c3a5ede7c27a"
    )


def test_authenticate_valid_key_returns_client_context(make_client):
    expected, key = make_client()

    assert auth.authenticate_client(key) == expected


def test_authenticate_strips_surrounding_whitespace(make_client):
    expected, key = make_client()

    assert auth.authenticate_client(f"  {key}\n") == expected


def test_authenticate_unknown_key_is_rejected(make_client):
    make_client()

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        auth.authenticate_client("ck_wrong")


@pytest.mark.parametrize("bad_key", [None, "", "   ", 123])
def test_authenticate_rejects_missing_or_malformed_key(bad_key, client_tables):
    with pytest.raises(AuthenticationError, match="required"):
        auth.authenticate_client(bad_key)


def test_authenticate_rejects_oversized_key_without_lookup(monkeypatch, client_tables):
    monkeypatch.setattr(storage, "get_client_by_key_hash", pytest.fail)

    with pytest.raises(AuthenticationError, match="Invalid API key"):
        auth.authenticate_client("k" * (auth.MAX_API_KEY_LENGTH + 1))


def test_missing_django_database_gives_actionable_error_and_is_not_created(
    db_path, django_db_path
):
    with pytest.raises(StorageError, match="manage.py migrate"):
        auth.authenticate_client("ck_anything")

    assert not django_db_path.exists()


def test_django_database_without_client_tables_gives_actionable_error(db_path, django_db_path):
    sqlite3.connect(django_db_path).close()

    with pytest.raises(StorageError, match=str(django_db_path)):
        auth.authenticate_client("ck_anything")


def test_other_database_errors_are_not_masked(db_path, django_db_path):
    with sqlite3.connect(django_db_path) as conn:
        conn.execute("CREATE TABLE api_keys (id TEXT, client_id TEXT, key_hash TEXT)")

    with pytest.raises(DBAPIError):
        auth.authenticate_client("ck_anything")


def test_core_opens_django_database_read_only(add_client):
    engine = storage.get_django_engine()
    try:
        with engine.connect() as conn, pytest.raises(DBAPIError, match="readonly"):
            conn.exec_driver_sql("DELETE FROM api_keys")
    finally:
        engine.dispose()


def test_client_tables_stay_out_of_core_database(db_path, add_client):
    add_client()

    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not tables & {"clients", "api_keys"}


# validate_client_project_access


CLIENT = auth.ClientContext("client-1", "alice", "proj-1")


def test_omitted_project_resolves_to_assigned_project():
    assert auth.validate_client_project_access(CLIENT, None) == "proj-1"


def test_matching_project_is_allowed():
    assert auth.validate_client_project_access(CLIENT, "proj-1") == "proj-1"


def test_other_project_is_denied():
    with pytest.raises(AuthorizationError, match="proj-2"):
        auth.validate_client_project_access(CLIENT, "proj-2")


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
    assert (row["status"], row["client_id"], row["project_id"]) == ("denied", None, "proj-1")


@pytest.mark.asyncio
async def test_invalid_key_is_denied_and_audited(make_client):
    make_client()
    calls, operation = recorder()

    with pytest.raises(AuthenticationError):
        await auth.guarded_call("log_decision", "ck_wrong", "proj-1", operation)

    assert calls == []
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "denied"
    assert row["client_id"] is None
    assert row["tool_name"] == "log_decision"
    assert row["error_message"] == "Invalid API key"


@pytest.mark.asyncio
async def test_key_is_verified_even_when_auth_not_required(make_client):
    make_client()
    _, operation = recorder()

    with pytest.raises(AuthenticationError):
        await auth.guarded_call("get_context", "ck_wrong", None, operation)


@pytest.mark.asyncio
async def test_project_mismatch_is_denied_and_audited(make_client):
    client, key = make_client()
    calls, operation = recorder()

    with pytest.raises(AuthorizationError):
        await auth.guarded_call("get_context", key, "proj-2", operation)

    assert calls == []
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "denied"
    assert (row["client_id"], row["user_id"], row["project_id"]) == (
        client.client_id, "alice", "proj-2",
    )


@pytest.mark.asyncio
async def test_success_runs_as_client_and_is_audited(make_client):
    client, key = make_client()
    calls, operation = recorder()

    assert await auth.guarded_call("get_context", key, None, operation) == "done"

    assert calls == [client]
    assert auth.current_client() is None
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "success"
    assert (row["client_id"], row["user_id"], row["project_id"]) == (
        client.client_id, "alice", "proj-1",
    )
    assert row["duration_ms"] >= 0
    assert row["error_message"] is None


@pytest.mark.asyncio
async def test_operation_error_is_audited_with_redacted_message(make_client):
    _, key = make_client()

    async def failing():
        raise ValueError("could not connect with password=hunter2")

    with pytest.raises(ValueError):
        await auth.guarded_call("update_state", key, "proj-1", failing)

    assert auth.current_client() is None
    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "error"
    assert "hunter2" not in row["error_message"]
    assert row["error_message"].startswith("ValueError:")


@pytest.mark.asyncio
async def test_audit_write_failure_does_not_fail_the_call(make_client, monkeypatch):
    _, key = make_client()
    _, operation = recorder()

    def broken(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(storage, "create_audit_log_entry", broken)

    assert await auth.guarded_call("get_context", key, None, operation) == "done"


def test_authenticate_request_requiring_key_denies_keyless_call(db_path):
    with pytest.raises(AuthenticationError, match="required"):
        auth.authenticate_request("get_context", None, "proj-1", key_required=True)

    [row] = audit_rows(db_path)
    assert (row["status"], row["client_id"]) == ("denied", None)


def test_authenticate_request_without_requirement_returns_none_for_keyless_call(db_path):
    assert auth.authenticate_request("get_context", None, None, key_required=False) is None
    assert audit_rows(db_path) == []


@pytest.mark.asyncio
async def test_run_as_client_uses_already_authenticated_client(make_client, monkeypatch):
    client, _ = make_client()
    monkeypatch.setattr(storage, "get_client_by_key_hash", pytest.fail)
    calls, operation = recorder()

    assert await auth.run_as_client("get_context", client, None, operation) == "done"

    assert calls == [client]
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


# services running as a client


@pytest.mark.asyncio
async def test_writes_record_client_user_and_assigned_project(make_client):
    client, key = make_client()

    async def work():
        decision = await services.log_decision(None, "Use Alembic", "Schema versioning")
        session = await services.log_session(None, "Added migrations")
        state = await services.update_state(None, "Auth core done", "MCP decorator")
        return decision, session, state

    decision, session, state = await auth.guarded_call("log_decision", key, None, work)

    assert (decision["project_id"], decision["client_id"], decision["user_id"]) == (
        "proj-1", client.client_id, "alice",
    )
    assert (session["project_id"], session["client_id"], session["user_id"]) == (
        "proj-1", client.client_id, "alice",
    )
    assert state["project_id"] == "proj-1"
    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT user_id FROM state").fetchone() == ("alice",)


@pytest.mark.asyncio
async def test_briefing_shows_which_client_wrote_each_record(make_client):
    client, key = make_client()

    async def work():
        await services.log_decision(None, "Use Alembic", "Schema versioning")
        await services.log_session(None, "Added migrations")
        return await services.get_briefing()

    briefing = await auth.guarded_call("get_context", key, None, work)

    assert briefing["project"]["id"] == "proj-1"
    assert briefing["decisions"][0]["client_id"] == client.client_id
    assert briefing["recent_sessions"][0]["client_id"] == client.client_id


@pytest.mark.asyncio
async def test_export_markdown_uses_assigned_project(make_client):
    _, key = make_client()

    markdown = await auth.guarded_call("export_markdown", key, None, services.export_markdown)

    assert "`proj-1`" in markdown


@pytest.mark.asyncio
async def test_services_reject_other_project_even_inside_guarded_call(make_client):
    _, key = make_client()

    async def sneaky():
        return await services.log_decision("proj-2", "Escalate", "Try another project")

    with pytest.raises(AuthorizationError):
        await auth.guarded_call("log_decision", key, None, sneaky)

    [row] = audit_rows(storage.get_db_path())
    assert row["status"] == "error"
    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone() == (0,)


@pytest.mark.asyncio
async def test_state_owner_is_updated_on_later_write(make_client):
    await services.update_state("proj-1", "Started locally", "Continue")
    _, key = make_client()

    async def work():
        return await services.update_state(None, "Continued as client", "Ship")

    await auth.guarded_call("update_state", key, None, work)

    with sqlite3.connect(storage.get_db_path()) as conn:
        assert conn.execute("SELECT user_id, progress FROM state").fetchall() == [
            ("alice", "Continued as client")
        ]


@pytest.mark.asyncio
async def test_local_mode_writes_keep_default_user_and_no_client(db_path):
    decision = await services.log_decision("proj-1", "Local", "No client")

    assert decision["client_id"] is None
    assert decision["user_id"]
