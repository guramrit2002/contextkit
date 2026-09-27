from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from core.auth import ClientContext, hash_api_key
from core.models import ApiKey, Client, DjangoOwnedBase


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    """Tests run on SQLite in local mode, even though .env may hold a real DATABASE_URL."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CONTEXTKIT_HOSTED", raising=False)


@pytest.fixture(autouse=True)
def django_db_path(tmp_path, monkeypatch):
    """Every test gets its own (initially absent) Django database, never the real one."""
    path = tmp_path / "django.sqlite3"
    monkeypatch.setenv("DJANGO_DB_PATH", str(path))
    return path


@pytest.fixture()
def add_client(django_db_path):
    """Stand-in for Django's migration and create_client: clients/api_keys in Django's file."""
    engine = create_engine(f"sqlite:///{django_db_path}", poolclass=NullPool)
    DjangoOwnedBase.metadata.create_all(engine)

    def _add(user_id="alice", project_id="proj-1", api_key="ck_alice_key", client_id=None):
        client_id = client_id or f"client-{user_id}-{project_id}"
        now = datetime.now(UTC)
        with Session(engine) as session:
            session.add(Client(
                id=client_id, user_id=user_id, project_id=project_id, name=user_id,
                created_at=now, updated_at=now,
            ))
            session.add(ApiKey(
                id=f"key-{client_id}", client_id=client_id,
                key_hash=hash_api_key(api_key), created_at=now,
            ))
            session.commit()
        return ClientContext(client_id, user_id, project_id), api_key

    yield _add
    engine.dispose()
