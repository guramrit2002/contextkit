# Implementation Spec: Horizon deployment

**Created:** 2026-09-28
**Status:** Ready for implementation
**Context:** ADR 026 (read it first), ADR 008, 019, 022, 025

---

## Overview

Make the MCP server deployable on Prefect Horizon against Supabase Postgres, while keeping local stdio mode with SQLite working exactly as it does today.

The end state: a user runs

```bash
claude mcp add --transport http contextkit https://<name>.fastmcp.app/mcp \
  --header "Authorization: Bearer ck_..."
```

and every tool call is authenticated, restricted to the client's project, written to Supabase, and audited.

**Decisions already made (don't revisit):**
- One Postgres database for core and Django tables.
- Horizon auth off; our API keys only.
- One client per project, as today.
- Supabase session-mode pooler URL.

---

## Configuration

| Variable | Where | Meaning |
|---|---|---|
| `DATABASE_URL` | Horizon env, local `.env` | Postgres URL (Supabase session pooler, `sslmode=require`). Unset means local SQLite mode. |
| `CONTEXTKIT_HOSTED` | Horizon env | `true` turns on hosted behavior (see §3). |
| `CONTEXTKIT_DB_PATH`, `DJANGO_DB_PATH` | local only | Unchanged: the SQLite files when `DATABASE_URL` is unset. |

The developer's local `.env` already holds a working Supabase session-pooler `DATABASE_URL`. `psycopg` 3.3.6 is already installed in the venv, but not yet declared in `pyproject.toml`.

---

## 1. Entrypoint and startup (deploy blocker)

**Problem:** `mcp_server/server.py` only defines `setup_tools()`; tools are registered in `mcp_server/__main__.py`. Horizon imports a `file.py:obj` entrypoint, so it would get a server with no tools.

- `mcp_server/server.py`:
  - Register the 5 tools at import time: call `setup_tools()` at module level, guarded so it runs once.
  - Create the server as `FastMCP("contextkit", instructions=...)`. FastMCP 4.x accepts `instructions`. The text tells agents to call `get_context` at the start of a task, `log_decision` / `update_state` while working, and `log_session` before finishing.
- New repo-root **`server.py`**: `from mcp_server.server import mcp`. This is the Horizon entrypoint (`server.py:mcp`). Loading `mcp_server/server.py` directly as a file would break its relative `from . import tools`.
- **Startup schema check (hosted only):**
  - Don't run migrations on start; replicas would race.
  - When `CONTEXTKIT_HOSTED` is true, check `core.db_init.core_schema_status()` at import and raise a clear error if the database isn't at head.
  - `mcp_server/__main__.py` (local stdio) keeps calling `initialize_database()` as today.
- `core/db_init.py`: change `UPGRADE_COMMAND` to plain `alembic upgrade head` (no `uv`).

## 2. Database URL instead of file paths (deploy blocker)

### `core/config.py`
- `resolve_database_url() -> str`: `DATABASE_URL` if set, else `f"sqlite:///{resolve_db_path()}"`.
- `resolve_django_database_url() -> str`: `DATABASE_URL` if set (one database), else the Django SQLite file URL.
- `is_sqlite(url) -> bool` helper.
- Keep `resolve_db_path` / `resolve_django_db_path` for local mode and the existing tests.
- Normalize `postgres://` / `postgresql://` to `postgresql+psycopg://` for SQLAlchemy.

### `core/storage.py`
- `get_engine()`:
  - Build from `resolve_database_url()` and cache one engine per process (module-level, keyed by URL so tests that change env still work).
  - Postgres: `pool_size=5`, `max_overflow=5`, `pool_pre_ping=True`. Keep it small; the Supavisor session pooler has a connection cap.
  - SQLite: `NullPool`, as today.
- `get_session()`: reuse a cached `sessionmaker` bound to that engine.
- `_alembic_config()`: `sqlalchemy.url` = `resolve_database_url()`.
- `get_django_engine()`:
  - SQLite: unchanged (`mode=ro` URI).
  - Postgres: return the core engine (same database).
- `get_client_by_key_hash()`:
  - On Postgres, execute `SET TRANSACTION READ ONLY` as the first statement of the lookup transaction.
  - Keeps the guarantee that core never writes Django's tables. It works through the pooler; don't rely on connect-time `options`.
- `_client_tables_missing()`: only check the file exists for SQLite. Update the error message to mention `DATABASE_URL`.
- Stop calling `engine.dispose()` on the shared engine. It's currently disposed in `get_client_by_key_hash` and `init_db`; only dispose engines you created for a one-off.

### `core/migrations/env.py`
- `_database_url()` fallback → `resolve_database_url()`.

### `core/db_init.py`
- `core_schema_status()`: the "file doesn't exist" shortcut applies only to SQLite.

### `api/api/settings.py`
- `DATABASES`:
  - If `DATABASE_URL` is set, use `dj_database_url.parse(url, conn_max_age=60, ssl_require=True)`.
  - Otherwise keep the current SQLite config, including the `TEST` name.
  - Add `dj-database-url` to the `backend` extra.
- Don't touch the `SECRET_KEY` / `DEBUG` / `ALLOWED_HOSTS` lines.

### `pyproject.toml`
- `dependencies`:
  - add `psycopg[binary]>=3.1` (Horizon installs from pyproject);
  - add `python-dotenv>=1.0`;
  - pin `fastmcp>=4,<5`. The code uses `fastmcp.server.dependencies.get_http_request`, and 4.0.5 is installed. The current `>=0.1.0` is too loose.
- `backend` extra: add `dj-database-url>=2.1`.

### Timezone
Columns are naive `DateTime`; `core.models.utc_now` writes aware UTC values. Supabase sessions are UTC (verified), so values store correctly. No code change; don't add connect-time `options`.

## 3. Hosted-only behavior (security and correctness)

### `core/config.py`
- `Config.is_hosted()`: `CONTEXTKIT_HOSTED` == `true`, read per call like `auth_required()`.
- `Config.auth_required()`: return True if hosted, otherwise the current `REQUIRE_AUTH` check.

### `core/storage.py`
- `detect_project_id()`: when hosted, raise `core.errors.ValidationError("project_id is required")`. Don't return the server's git remote or working directory. Authenticated calls never reach this, because `core.services._resolve_identity` takes the client's project.
- `get_or_create_project()`: when hosted, don't run `git` or read `os.getcwd()`.
  - Set `git_remote` to `project_id` if it looks like a URL (`http(s)://`, `git@`, `ssh://`); otherwise `None`.
  - Set `local_path` to `None`.
  - `name` is unchanged.

### `mcp_server/auth_middleware.py`
- Add `is_http_request() -> bool` (`_http_headers() is not None`).

### `mcp_server/tools.py`
- In `export_markdown` and `export_markdown_flat`, when `is_http_request()` is true and `output_path` is set, raise `ValueError("output_path is not supported over HTTP; use the returned markdown")` and don't write anything.
- stdio keeps writing the file. This stays in the transport layer, where the file write already lives (`docs/CLAUDE.md` rule 2).

## 4. Config and docs

- `.env.example`: document `DATABASE_URL` (session pooler format, `sslmode=require`, no brackets, URL-encode special characters) and `CONTEXTKIT_HOSTED`.
- README:
  - Add a "Hosted" section with the `claude mcp add --transport http ... --header` command and the Cursor/Codex JSON equivalents.
  - Keep the local section.
  - Fix the clone and repository URLs (currently `github.com/anthropics/contextkit`; should be `github.com/guramrit2002/contextkit`) in `README.md` and `pyproject.toml` `[project.urls]`.
- `docs/CLAUDE.md` tech stack table: database row becomes "SQLite locally, Postgres (Supabase) when hosted".

## 5. Tests

Add to `tests/`, following existing patterns in `tests/test_db_path.py`, `tests/test_mcp_auth.py` and `tests/conftest.py`:

- **URL resolution:**
  - `DATABASE_URL` unset gives the SQLite URLs for core and Django;
  - set gives the same Postgres URL for both;
  - `postgres://` is normalized.
- **Engine selection** (no live database; inspect the engine):
  - a SQLite URL gives `NullPool`;
  - a Postgres URL gives a `QueuePool` with `pool_pre_ping`;
  - the engine is cached per URL.
- **Read-only lookup:** with a Postgres-dialect engine, a `before_cursor_execute` listener sees `SET TRANSACTION READ ONLY` before the key query. Or mark it for the live check below if it can't be unit-tested cleanly.
- **Entrypoint:** importing `server` (repo root) and `mcp_server.server` exposes exactly the 5 tools (`get_context`, `log_decision`, `update_state`, `log_session`, `export_markdown`), and importing twice doesn't double-register.
- **Hosted flag:**
  - `auth_required()` is true even with `REQUIRE_AUTH` unset;
  - `detect_project_id()` raises;
  - `get_or_create_project()` never calls `subprocess` (patch it and assert not called) and stores `git_remote` from the project ID.
- **Export over HTTP:** with `_http_headers` patched to return headers, `output_path` raises and no file is created. Over stdio the file is still written (existing test).

Both suites must pass: `pytest` and `cd api && python manage.py test`.

---

## Deploy steps (after merge to `main`)

These are for the developer, not the coding session.

1. **Supabase:** disable the Data API in project settings, and make sure `DATABASE_URL` ends with `?sslmode=require`.
2. **Migrate from a local machine,** with `DATABASE_URL` set:
   - `alembic upgrade head`
   - `cd api && python manage.py migrate`
3. **Create a client:** `python manage.py create_client --project-id <exact git remote> --name <name>`. Save the key.
4. **Horizon:**
   - repo `guramrit2002/contextkit`, entrypoint `server.py:mcp`;
   - env `DATABASE_URL`, `CONTEXTKIT_HOSTED=true`;
   - authentication **off**.
5. **On a preview deploy,** confirm:
   - a call with the key succeeds and shows up in `audit_log` with its `client_id`;
   - a call without a key is denied.

   This also answers ADR 026's open question about header forwarding.

---

## Implementation checklist

- [ ] §1: tools registered at import, `instructions`, root `server.py`, hosted schema check, `UPGRADE_COMMAND`
- [ ] §2: `resolve_database_url` family, cached engines, Alembic URL, read-only lookup, Django `DATABASES`, `pyproject` deps
- [ ] §3: `is_hosted`, auth forced when hosted, no git/cwd when hosted, no file writes over HTTP
- [ ] §4: `.env.example`, README hosted section and URL fixes, CLAUDE.md stack row
- [ ] §5: tests; both suites green
- [ ] Local stdio MCP still works in Claude Code after `/mcp` reconnect (SQLite, `CONTEXTKIT_API_KEY`)
- [ ] Live check against Supabase: run both migrations; `fastmcp run server.py:mcp --transport http` with `CONTEXTKIT_HOSTED=true`; call all 5 tools with a Bearer key via MCP Inspector or `curl`; rows and `audit_log` appear in Supabase; keyless call denied; `export_markdown` with `output_path` rejected

---

## Success criteria

- `fastmcp inspect server.py:mcp` lists 5 tools and the instructions.
- With `DATABASE_URL` set, both migrations create their tables in Supabase, and core's `alembic_version` is at head.
- With `CONTEXTKIT_HOSTED=true` over HTTP:
  - keyless calls are denied and audited;
  - keyed calls work and are restricted to the client's project;
  - no files are written on the server;
  - no `git` subprocess runs.
- With `DATABASE_URL` unset, behavior is identical to today (SQLite, stdio, all existing tests pass).
- The key lookup can't write Django's tables on either backend.

---

## Out of scope

- Per-user keys and ADR 012 normalization.
- Hosting Django.
- Rate limiting and key rotation.
- Row Level Security.
- `timestamptz` migration.
- Async database access.
- Changing the tool signatures (flat vs `input` object).
