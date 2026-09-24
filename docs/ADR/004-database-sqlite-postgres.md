# ADR 004 — SQLite locally, Postgres when hosted

**Status:** Accepted

## Context

Step 1 is a single-user local tool. A lightweight database that needs no server is ideal. Step 2 is a hosted multi-user service that needs concurrent writers and is already running Postgres for Django.

## Decision

Use SQLite for local development and step 1. Migrate to Postgres for the hosted deployment in step 2. The switch is a configuration change in `core/storage.py`, not a code change.

## Consequences

- No database server required for local use.
- SQLAlchemy abstracts the engine so the same queries run on both databases.
- SQLite FTS5 handles keyword search locally; Postgres full-text search handles it when hosted.
- SQLite's single-writer limitation is acceptable for one user; Postgres handles concurrent writers when hosted.
