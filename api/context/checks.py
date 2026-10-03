"""
Startup check: the REST views run core services against core's database, whose schema is
migrated by Alembic (ADR 008), never by Django. Fail fast when it is behind the code.
"""
from django.core import checks
from sqlalchemy.exc import DBAPIError

from core.config import describe_core_database
from core.db_init import UPGRADE_COMMAND, core_schema_status


def core_database_schema(app_configs, **kwargs):
    try:
        status = core_schema_status()
    except DBAPIError as exc:
        # Report it as one clear error. The exception type only: messages can include the
        # host, and the URL itself holds the password.
        return [checks.Error(
            f"Could not connect to the core database ({type(exc.orig).__name__}).",
            hint="Check DATABASE_URL, the network, and that the database is running.",
            id="context.E002",
        )]
    if status.up_to_date:
        return []
    if not status.initialized:
        # Warning, not error: a fresh clone must still be able to run Django migrate and tests.
        return [checks.Warning(
            f"Core database ({describe_core_database()}) is not initialized.",
            hint=f"Run `{UPGRADE_COMMAND}` from the repo root before serving requests.",
            id="context.W001",
        )]
    current = status.current or "none (pre-Alembic)"
    return [checks.Error(
        f"Core database ({describe_core_database()}) is at migration {current}, "
        f"but the code needs {status.head}.",
        hint=f"Run `{UPGRADE_COMMAND}`.",
        id="context.E001",
    )]
