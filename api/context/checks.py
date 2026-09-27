"""
Startup check: the REST views run core services against core's database, whose schema is
migrated by Alembic (ADR 008), never by Django. Fail fast when it is behind the code.
"""
from django.core import checks

from core.config import resolve_db_path
from core.db_init import UPGRADE_COMMAND, core_schema_status


def core_database_schema(app_configs, **kwargs):
    status = core_schema_status()
    if status.up_to_date:
        return []
    if not status.initialized:
        # Warning, not error: a fresh clone must still be able to run Django migrate and tests.
        return [checks.Warning(
            f"Core database {resolve_db_path()} is not initialized.",
            hint=f"Run `{UPGRADE_COMMAND}` from the repo root before serving requests.",
            id="context.W001",
        )]
    current = status.current or "none (pre-Alembic)"
    return [checks.Error(
        f"Core database {resolve_db_path()} is at migration {current}, "
        f"but the code needs {status.head}.",
        hint=f"Run `{UPGRADE_COMMAND}`.",
        id="context.E001",
    )]
