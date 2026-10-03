import sqlite3

import pytest
from alembic import command

from core import storage
from core.db_init import core_schema_status

HEAD = "0004"


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "core.sqlite3"
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(path))
    return path


def test_missing_database_is_not_initialized_and_not_created(db_path):
    status = core_schema_status()

    assert (status.current, status.head, status.initialized) == (None, HEAD, False)
    assert not db_path.exists()


def test_migrated_database_is_up_to_date(db_path):
    storage.init_db()

    status = core_schema_status()

    assert status.up_to_date
    assert status.current == HEAD


def test_database_behind_head_reports_its_revision(db_path):
    command.upgrade(storage._alembic_config(), "0002")

    status = core_schema_status()

    assert (status.current, status.up_to_date, status.initialized) == ("0002", False, True)


def test_pre_alembic_database_counts_as_initialized_but_behind(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")

    status = core_schema_status()

    assert (status.current, status.initialized, status.up_to_date) == (None, True, False)


def test_empty_database_file_is_not_initialized(db_path):
    sqlite3.connect(db_path).close()

    assert not core_schema_status().initialized
