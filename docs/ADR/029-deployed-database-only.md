# ADR 029 — Run only against the deployed database

**Status:** Accepted

**Amends:** ADR 015 (local storage location), ADR 026 (local mode kept "exactly as today")

## Context

ADR 026 kept a local mode: with `DATABASE_URL` unset, the MCP server and Django fell back to two SQLite files. In practice contextkit now runs only as deployed services (the MCP server on Render, Django on EC2) against one Supabase Postgres database, and local-database support is not being worked on.

The silent fallback became a trap. A server started without `DATABASE_URL` (a missing env var on a deploy, a fresh clone) still started, wrote context to a throwaway SQLite file nobody reads, and reported success.

## Decision

- `DATABASE_URL` is **required**. Without it, `core.config.resolve_database_url()` raises `ConfigurationError`, the MCP server fails on import (before registering tools), and Django's settings raise `ImproperlyConfigured`. The message names the setting but never prints a URL.
- SQLite remains only as an explicit, **test-only** opt-in: `CONTEXTKIT_ALLOW_SQLITE=true`. The pytest suite and `manage.py test` set it themselves, so tests stay fast, isolated, and never touch the deployed database. The Docker build sets it for the `collectstatic` step only (which opens no database); it is not set in the image.
- Django's startup check reports an unreachable database as one error (`context.E002`, exception type only) instead of a traceback that can include the host.
- The README and `.env.example` no longer describe a local-SQLite mode or claim that data stays on the user's machine.

## Consequences

- A misconfigured deploy fails at startup instead of quietly losing data.
- Development and every `manage.py` command need the deployed `DATABASE_URL` (in `.env`); there is no offline mode.
- The SQLite code paths (`CONTEXTKIT_DB_PATH`, `DJANGO_DB_PATH`, the read-only SQLite key lookup) stay, used only by the tests.

## Deferred

- A separate Postgres for CI and staging, which would let the tests run on Postgres too.
