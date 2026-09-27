"""Initialize the database with tables."""
import logging
from typing import NamedTuple, Optional

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from core.config import is_sqlite, resolve_database_url, resolve_db_path
from core.storage import _alembic_config, get_engine, init_db

logger = logging.getLogger(__name__)

UPGRADE_COMMAND = "alembic upgrade head"


class SchemaStatus(NamedTuple):
    current: Optional[str]
    head: str
    has_tables: bool

    @property
    def up_to_date(self) -> bool:
        return self.current == self.head

    @property
    def initialized(self) -> bool:
        # Tables without a revision means a pre-Alembic database: present, but behind.
        return self.current is not None or self.has_tables


def core_schema_status() -> SchemaStatus:
    """Core database revision vs. the latest migration. Never creates a SQLite file."""
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    if is_sqlite(resolve_database_url()) and not resolve_db_path().exists():
        return SchemaStatus(None, head, has_tables=False)
    with get_engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        has_tables = inspect(conn).has_table("projects")
    return SchemaStatus(current, head, has_tables)


def initialize_database():
    """Create all database tables."""
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
