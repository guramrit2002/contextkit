import pytest

from core import config


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite:////home/me/core.sqlite3", "SQLite file /home/me/core.sqlite3"),
        ("postgresql+psycopg://u:pw@host:5432/db", "Postgres database from DATABASE_URL"),
        ("postgresql://u:pw@host/db", "Postgres database from DATABASE_URL"),
        ("postgres://u:pw@host/db", "Postgres database from DATABASE_URL"),
        ("mysql://u:pw@host/db", "database from DATABASE_URL"),
    ],
)
def test_describes_a_database_without_its_url(url, expected):
    description = config.describe_database_url(url)

    assert description == expected
    assert "pw" not in description and "host" not in description


def test_describe_core_database_follows_the_configured_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:secret@pooler.example.com/postgres")

    assert config.describe_core_database() == "Postgres database from DATABASE_URL"


def test_describe_core_database_names_the_sqlite_test_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CONTEXTKIT_ALLOW_SQLITE", "true")
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(tmp_path / "core.sqlite3"))

    assert config.describe_core_database() == f"SQLite file {tmp_path / 'core.sqlite3'}"
