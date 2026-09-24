# ADR 008 — Table ownership split between core and Django

**Status:** Accepted

## Context

Core and Django share one database in the hosted deployment. Both have their own ORM (SQLAlchemy and Django ORM). Without a clear ownership rule, migrations will conflict.

## Decision

| Owner | Tables |
|---|---|
| Core | projects, decisions, state, sessions |
| Django | users, api_keys, analytics_events |

Core manages its tables through Alembic. Django manages its tables through its own migrations. Django declares core's tables as `managed = False` so it can query them without trying to create or alter them.

## Consequences

- No migration conflicts between Alembic and Django.
- When a core table changes, the matching `managed = False` model in Django must be updated manually.
- Django can join across both sets of tables in read queries because they share one database.
