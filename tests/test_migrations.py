import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

from core import storage
from core.migrations import include_name
from core.models import Base

HEAD = "0003"

LEGACY_SCHEMA = """
CREATE TABLE projects (
    id VARCHAR(500) PRIMARY KEY, name VARCHAR(255) NOT NULL, git_remote VARCHAR(500),
    local_path VARCHAR(500), user_id VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL,
    updated_at DATETIME
);
CREATE TABLE decisions (
    id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(500) NOT NULL REFERENCES projects(id),
    user_id VARCHAR(255) NOT NULL, decision TEXT NOT NULL, reasoning TEXT NOT NULL,
    alternatives_considered TEXT, created_at DATETIME NOT NULL
);
CREATE TABLE state (
    id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(500) NOT NULL UNIQUE REFERENCES projects(id),
    user_id VARCHAR(255) NOT NULL, progress TEXT NOT NULL, next_steps TEXT NOT NULL,
    blockers TEXT, updated_at DATETIME, created_at DATETIME
);
CREATE TABLE sessions (
    id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(500) NOT NULL REFERENCES projects(id),
    user_id VARCHAR(255) NOT NULL, summary TEXT NOT NULL, decisions_made TEXT,
    created_at DATETIME NOT NULL
);
INSERT INTO projects VALUES ('p1', 'p1', NULL, '/tmp', 'u1', '2026-01-01', '2026-01-01');
INSERT INTO decisions VALUES ('d1', 'p1', 'u1', 'Use SQLite', 'Simple', NULL, '2026-01-01');
INSERT INTO sessions VALUES ('s1', 'p1', 'u1', 'Built storage', NULL, '2026-01-01');
"""


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "contextkit.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    return path


def _inspector(path):
    return inspect(create_engine(f"sqlite:///{path}", poolclass=NullPool))


def _columns(path, table):
    return {c["name"] for c in _inspector(path).get_columns(table)}


def _revision(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_fresh_database_is_migrated_to_head(db_path):
    storage.init_db()

    tables = set(_inspector(db_path).get_table_names())
    assert {"projects", "decisions", "state", "sessions", "audit_log"} <= tables
    assert "client_id" in _columns(db_path, "decisions")
    assert "client_id" in _columns(db_path, "sessions")
    assert _revision(db_path) == HEAD


def test_audit_log_indexes_exist(db_path):
    storage.init_db()

    indexes = {i["name"] for i in _inspector(db_path).get_indexes("audit_log")}
    assert indexes == {
        "ix_audit_log_client_id_timestamp",
        "ix_audit_log_project_id_timestamp",
        "ix_audit_log_user_id_timestamp",
    }


def test_pre_alembic_database_is_upgraded_and_keeps_data(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(LEGACY_SCHEMA)

    storage.init_db()

    assert "client_id" in _columns(db_path, "decisions")
    assert _revision(db_path) == HEAD
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT decision, client_id FROM decisions").fetchall() == [
            ("Use SQLite", None)
        ]
        assert conn.execute("SELECT summary FROM sessions").fetchall() == [("Built storage",)]


def test_pre_alembic_database_that_already_has_agent_id_is_upgraded(db_path):
    # create_all() on the 0002-era models added agent_id before Alembic managed the schema.
    with sqlite3.connect(db_path) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute("ALTER TABLE decisions ADD COLUMN agent_id VARCHAR(36)")
        conn.execute("ALTER TABLE sessions ADD COLUMN agent_id VARCHAR(36)")
        conn.execute("UPDATE decisions SET agent_id = 'a-1'")

    storage.init_db()

    assert "audit_log" in _inspector(db_path).get_table_names()
    assert _revision(db_path) == HEAD
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT client_id FROM decisions").fetchall() == [("a-1",)]


def _seed_agent_ids(path):
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO projects VALUES ('p1','p1',NULL,'/tmp','u1','2026-01-01',NULL)")
        conn.execute(
            "INSERT INTO decisions (id, project_id, user_id, agent_id, decision, reasoning, "
            "created_at) VALUES ('d1','p1','u1','a-1','D','R','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO sessions (id, project_id, user_id, agent_id, summary, created_at) "
            "VALUES ('s1','p1','u1','a-1','S','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO audit_log (id, agent_id, tool_name, timestamp, status) "
            "VALUES ('e1','a-1','get_context','2026-01-01','success')"
        )


def test_rename_to_client_id_keeps_existing_values(db_path):
    command.upgrade(storage._alembic_config(), "0002")
    _seed_agent_ids(db_path)

    command.upgrade(storage._alembic_config(), "0003")

    for table in ("decisions", "sessions", "audit_log"):
        columns = _columns(db_path, table)
        assert "client_id" in columns and "agent_id" not in columns
        with sqlite3.connect(db_path) as conn:
            assert conn.execute(f"SELECT client_id FROM {table}").fetchall() == [("a-1",)]


def test_downgrade_from_client_id_restores_agent_id(db_path):
    command.upgrade(storage._alembic_config(), "0002")
    _seed_agent_ids(db_path)
    command.upgrade(storage._alembic_config(), "0003")

    command.downgrade(storage._alembic_config(), "0002")

    indexes = {i["name"] for i in _inspector(db_path).get_indexes("audit_log")}
    assert "ix_audit_log_agent_id_timestamp" in indexes
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT agent_id FROM audit_log").fetchall() == [("a-1",)]


def test_init_db_is_idempotent(db_path):
    storage.init_db()
    storage.init_db()

    assert _revision(db_path) == HEAD


def test_downgrade_to_baseline_removes_agent_auth_schema(db_path):
    storage.init_db()

    command.downgrade(storage._alembic_config(), "0001")

    assert "audit_log" not in _inspector(db_path).get_table_names()
    assert "client_id" not in _columns(db_path, "decisions")
    assert "client_id" not in _columns(db_path, "sessions")


def test_downgrade_to_base_drops_all_core_tables(db_path):
    storage.init_db()

    command.downgrade(storage._alembic_config(), "base")

    assert set(_inspector(db_path).get_table_names()) == {"alembic_version"}


def _autogenerate_diff(path):
    engine = create_engine(f"sqlite:///{path}", poolclass=NullPool)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"include_name": include_name})
            return compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()


def test_models_match_migrations(db_path):
    storage.init_db()

    assert _autogenerate_diff(db_path) == []


def test_autogenerate_ignores_django_owned_tables(db_path):
    storage.init_db()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            "CREATE TABLE clients (id VARCHAR(36) PRIMARY KEY);"
            "CREATE TABLE api_keys (id VARCHAR(36) PRIMARY KEY, key_hash VARCHAR(64));"
            "CREATE INDEX ix_api_keys_hash ON api_keys (key_hash);"
        )

    assert _autogenerate_diff(db_path) == []


def test_alembic_ini_resolves_database_from_environment(db_path):
    cfg = AlembicConfig("alembic.ini")

    command.upgrade(cfg, "head")

    assert _revision(db_path) == HEAD


def test_offline_mode_renders_sql(db_path, capsys):
    command.upgrade(storage._alembic_config(), "head", sql=True)

    output = capsys.readouterr().out
    assert "CREATE TABLE audit_log" in output
    assert not db_path.exists()
