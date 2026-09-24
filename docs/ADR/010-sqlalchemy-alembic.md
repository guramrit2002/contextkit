# ADR 010 — SQLAlchemy and Alembic for data access

**Status:** Proposed

## Context

Core needs database access. Options are raw `sqlite3`, SQLAlchemy, or another ORM. The database will move from SQLite to Postgres in step 2.

## Decision

Use SQLAlchemy Core or ORM for database access and Alembic for migrations. Both support SQLite and Postgres with the same code.

## Consequences

- Switching to Postgres is a connection string change, not a query rewrite.
- Alembic handles migration history independently of Django.
- SQLAlchemy adds a dependency but removes the need to write dialect-specific SQL.
- If rejected in favour of raw `sqlite3`, a query rewrite will be needed for step 2.
