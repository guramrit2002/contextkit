from pathlib import Path

from core import storage
from core.config import REPO_ROOT, resolve_db_path, resolve_django_db_path


def test_defaults_to_repo_root_database(monkeypatch):
    monkeypatch.delenv("CONTEXTKIT_DB_PATH", raising=False)

    assert resolve_db_path() == REPO_ROOT / "db.sqlite3"


def test_relative_path_resolves_from_repo_root(monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", "./data/ck.db")

    assert resolve_db_path() == (REPO_ROOT / "data" / "ck.db").resolve()


def test_relative_path_ignores_current_directory(monkeypatch, tmp_path):
    # Regression: running Django from api/ made core open api/db.sqlite3 instead.
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", "./db.sqlite3")
    monkeypatch.chdir(tmp_path)

    assert storage.get_db_path() == str(REPO_ROOT / "db.sqlite3")


def test_absolute_path_is_used_as_is(monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", "/var/lib/ck.db")

    assert resolve_db_path() == Path("/var/lib/ck.db")


def test_home_directory_is_expanded(monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", "~/.contextkit/contextkit.db")

    assert resolve_db_path() == Path.home() / ".contextkit" / "contextkit.db"


def test_django_database_defaults_to_api_folder(monkeypatch):
    monkeypatch.delenv("DJANGO_DB_PATH", raising=False)

    assert resolve_django_db_path() == REPO_ROOT / "api" / "db.sqlite3"


def test_django_database_relative_path_resolves_from_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DJANGO_DB_PATH", "./data/django.db")
    monkeypatch.chdir(tmp_path)

    assert resolve_django_db_path() == (REPO_ROOT / "data" / "django.db").resolve()


def test_core_and_django_default_to_different_files(monkeypatch):
    monkeypatch.delenv("CONTEXTKIT_DB_PATH", raising=False)
    monkeypatch.delenv("DJANGO_DB_PATH", raising=False)

    assert resolve_db_path() != resolve_django_db_path()
