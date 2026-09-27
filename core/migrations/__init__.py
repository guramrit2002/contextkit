"""Alembic migrations for core-owned tables."""
from core.models import Base


def include_name(name, type_, parent_names) -> bool:
    """Only core's tables are visible to Alembic; Django owns the rest of the shared database."""
    if type_ == "table":
        return name in Base.metadata.tables
    return True
