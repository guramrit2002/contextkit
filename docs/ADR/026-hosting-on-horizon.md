# ADR 026 — Host the MCP server on Horizon with Supabase Postgres

**Status:** Proposed

**Amends:** ADR 008 (database layout), ADR 015 (local storage location), ADR 019 (transport)

> **Hosting platform superseded by [ADR 027](027-hosting-on-render.md):** the server runs on Render, because Horizon's authentication could not be turned off on the free plan. The rest of this ADR (one Postgres database, `CONTEXTKIT_HOSTED`, API keys only, migrations as a deploy step) still applies.

## Context

The goal is a zero-install experience: a user gets an API key from the contextkit platform and adds a remote MCP URL to their agent (Claude Code, Cursor, Codex). No clone, no Python, no local database.

The MCP server will be hosted on Prefect Horizon. Horizon clones the GitHub repo, loads a FastMCP object from an entrypoint (`file.py:obj`, the same syntax as `fastmcp run`), serves it over HTTP at `https://<name>.fastmcp.app/mcp`, injects environment variables set in its UI, and redeploys on every push to `main`. It offers optional OAuth that admits only members of the Horizon organization.

The current code assumes the server runs on the user's machine:

- Tools are registered only in `mcp_server/__main__.py`, so loading `mcp_server/server.py:mcp` gives a server with no tools.
- Both databases are SQLite files (`core.sqlite3`, `api/django.sqlite3`). Neither exists or persists on Horizon.
- `export_markdown` writes to any path the caller gives it.
- Project detection and project creation shell out to `git` and read the working directory. On Horizon, that is contextkit's own clone.
- Calls without a key run in unaudited local mode unless `REQUIRE_AUTH` is set.

A Postgres database has been created on Supabase (region `ap-northeast-1`, Postgres 17, session timezone UTC).

## Decision

### Hosting split

- **Horizon** hosts only the MCP server.
- **Django** (sign-up and key issuing) is hosted separately, later. It is not needed for the first deploy: clients can be created with `manage.py create_client` run locally against the hosted database.
- **Supabase Postgres** is the single database for both.

### One Postgres database

Core's tables (Alembic) and Django's tables (Django migrations) live in the same Supabase database. Alembic's `include_name` filter already ignores tables it does not own, so each tool still migrates only its own tables (ADR 008's ownership rule holds; only the physical layout changes).

A single `DATABASE_URL` configures both. When it is unset, local mode keeps using the two SQLite files exactly as today.

Core must still never write Django's tables. On Postgres this is enforced per transaction with `SET TRANSACTION READ ONLY` on the key lookup, replacing SQLite's `mode=ro`.

### Supabase connection

- Use the **session-mode pooler** URL (`<ref>` user, `*.pooler.supabase.com`, port 5432, `sslmode=require`). The direct connection is IPv6-only, and Horizon and many networks can't reach it.
- Do not use transaction mode (port 6543). It breaks psycopg's prepared statements and session settings.
- The **Supabase Data API is disabled**. It would otherwise expose every `public` table, including `api_keys` and all context, to anyone holding the project's anon key.

### Authentication

Horizon's OAuth is **off** for this server. Clients authenticate with contextkit API keys (`Authorization: Bearer ck_...`), checked by `core.auth` as today. Horizon OAuth would admit only Horizon organization members, which rules out public users with platform-issued keys.

### Hosted mode switch

A single environment variable, `CONTEXTKIT_HOSTED=true`, marks a server as hosted. When set:

- Authentication is always required, regardless of `REQUIRE_AUTH`, so a missing setting cannot open the server.
- Project detection from the server's git remote or working directory is disabled.
- New projects never record the server's git remote or file paths.

`export_markdown` never writes files when called over HTTP, hosted or not. That is a transport rule, not a hosting rule.

### Migrations

Migrations run as a deploy step (`alembic upgrade head`, `manage.py migrate`), not on server start: several Horizon replicas starting together would race. The server checks the schema revision at start and fails with a clear message if it is behind.

### Agent instructions

The server sends MCP `instructions` telling agents to call `get_context` first and `log_session` before finishing. Users no longer need these rules in their repo's `CLAUDE.md`.

## Consequences

- Users connect with one command and a key; nothing to install.
- Local stdio mode with SQLite still works unchanged for development and self-hosting.
- Deploys follow `main`; `dev` → `main` merges become production releases.
- The Supabase password lives in Horizon's environment variables and local `.env` only.
- Every agent request now depends on Supabase being reachable.
- The README's "all data stays on your machine" claim no longer holds for hosted users. Secret redaction becomes more important (ADR 017 phase 2).
- Each client still covers exactly one project (ADR 022) for the first deploy.

## Deferred

- Per-user keys with the project sent per call, together with the ADR 012 project-ID normalization fix.
- Hosting Django (sign-up and key UI) and user APIs (ADR 024).
- Rate limiting and key rotation.
- Row Level Security on every table, as defense in depth once the Data API is off.
- Moving to `timestamptz` columns.
- Moving the synchronous database calls out of the async tool handlers.

## Open questions

- Does Horizon pass the `Authorization` header through to the server when its own auth is off? To be confirmed on a preview deploy before the first release.
- Where will Django be hosted?
