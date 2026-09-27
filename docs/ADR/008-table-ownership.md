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

## Update (2026-09-27): separate database files

Core and Django no longer share one SQLite file locally:

| Database | Setting | Default | Tables |
|---|---|---|---|
| Core | `CONTEXTKIT_DB_PATH` | `./core.sqlite3` | projects, decisions, state, sessions, audit_log |
| Django | `DJANGO_DB_PATH` | `./api/django.sqlite3` | clients, api_keys, auth_*, django_* |

Relative paths resolve from the repo root (`core.config`), and Django's settings use the same
resolver, so every process opens the same files regardless of its working directory.

- Core verifies client API keys (ADR 025) by opening Django's file **read-only** (SQLite `mode=ro`), so
  core cannot write Django's tables and a missing file is an error rather than a new empty file.
- Django can no longer join across core and Django tables in one query. Dashboards that need
  core data must read it through a second database alias (or core services), not a join.
- Hosted deployments may still point both settings at one Postgres database; the ownership rules
  above are unchanged either way.
