"""Configuration management for contextkit."""
import os
from pathlib import Path
from typing import Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve(env_var: str, default: str) -> Path:
    # Relative paths come from the repo root, never the current directory, so every process
    # (MCP server, Django from api/, tests) opens the same file.
    configured = os.getenv(env_var)
    if not configured:
        return REPO_ROOT / default
    path = Path(configured).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def resolve_db_path() -> Path:
    """Core's database: projects, decisions, state, sessions, audit_log."""
    return _resolve("CONTEXTKIT_DB_PATH", "core.sqlite3")


def resolve_django_db_path() -> Path:
    """Django's database: clients, api_keys, auth. Core opens it read-only to verify keys."""
    return _resolve("DJANGO_DB_PATH", "api/django.sqlite3")


POSTGRES_SCHEMES = ("postgres://", "postgresql://")
POSTGRES_DRIVER = "postgresql+psycopg://"


def _database_url_env() -> Optional[str]:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    for scheme in POSTGRES_SCHEMES:
        if url.startswith(scheme):
            return POSTGRES_DRIVER + url[len(scheme):]
    return url


MISSING_DATABASE_URL = (
    "DATABASE_URL is not set. contextkit runs only against the deployed Postgres database "
    "(ADR 029): set DATABASE_URL to the Supabase session-pooler URL (see .env.example)."
)


def sqlite_allowed() -> bool:
    """SQLite is for the test suites only, which opt in with CONTEXTKIT_ALLOW_SQLITE=true."""
    return os.getenv("CONTEXTKIT_ALLOW_SQLITE", "False").lower() == "true"


def _require(sqlite_url: str) -> str:
    url = _database_url_env()
    if url:
        return url
    if sqlite_allowed():
        return sqlite_url
    from core.errors import ConfigurationError

    raise ConfigurationError(MISSING_DATABASE_URL)


def resolve_database_url() -> str:
    """Core's database URL: DATABASE_URL. Tests may use a SQLite file instead."""
    return _require(f"sqlite:///{resolve_db_path()}")


def resolve_django_database_url() -> str:
    """Django's database URL: the same DATABASE_URL. Tests may use a SQLite file instead."""
    return _require(f"sqlite:///{resolve_django_db_path()}")


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def describe_database_url(url: str) -> str:
    """
    Name a database for messages without revealing it: never the URL, which holds the password.

    SQLite gets its file path; anything else only its kind and where it was configured.
    """
    if is_sqlite(url):
        return f"SQLite file {url.split(':///', 1)[-1]}"
    if url.startswith(POSTGRES_DRIVER) or url.startswith(POSTGRES_SCHEMES):
        return "Postgres database from DATABASE_URL"
    return "database from DATABASE_URL"


def describe_core_database() -> str:
    """The core database in use, for messages: e.g. "Postgres database from DATABASE_URL"."""
    return describe_database_url(resolve_database_url())


class Config:
    """Application configuration loaded from environment variables."""

    DEFAULT_USER_ID: str = os.getenv("DEFAULT_USER_ID", "default_user")

    @classmethod
    def get_default_user_id(cls) -> str:
        """Get the default user ID for single-user mode."""
        return cls.DEFAULT_USER_ID

    @staticmethod
    def is_hosted() -> bool:
        """CONTEXTKIT_HOSTED=true marks a hosted server (ADR 026). Read per call."""
        return os.getenv("CONTEXTKIT_HOSTED", "False").lower() == "true"

    @staticmethod
    def auth_required() -> bool:
        """Whether tool calls without an API key are rejected. Always true when hosted."""
        if Config.is_hosted():
            return True
        return os.getenv("REQUIRE_AUTH", "False").lower() == "true"


# Create a singleton instance
config = Config()
