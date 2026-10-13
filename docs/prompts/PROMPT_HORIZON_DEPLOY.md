# Coding Agent Prompt: Horizon deployment

**Status:** Ready
**Spec:** `docs/spec/SPEC_HORIZON_DEPLOY.md`
**ADR:** `docs/adr/026-hosting-on-horizon.md`

Copy everything in the block below into a fresh coding session.

---

```
You are implementing a feature for contextkit based on a written spec. Read
everything below before writing any code.

## 1. Project rules

Read `docs/CLAUDE.md`. Its rules are non-negotiable:
- `core/` has no framework imports.
- MCP tools are thin wrappers that call one `core.services` function.
- Only core writes the context tables.
- Django writes context only through core.

## 2. Your spec

Read `docs/spec/SPEC_HORIZON_DEPLOY.md` in full. It is the source of truth:
- what changes in which file;
- which existing functions to reuse;
- the tests to add;
- the checklist and success criteria.

The goal: make the MCP server deployable on Prefect Horizon against Supabase
Postgres, while local stdio mode with SQLite keeps working exactly as today.

## 3. Architecture decisions

Read `docs/adr/026-hosting-on-horizon.md` for why:
- one Postgres database;
- Horizon auth off, our API keys only;
- the CONTEXTKIT_HOSTED switch;
- migrations as a deploy step.

Also skim ADR 008 (table ownership), ADR 022 (client auth) and ADR 025
(client naming). Don't change those decisions.

## 4. Existing code to reuse

- core/config.py: resolve_db_path, resolve_django_db_path, Config.auth_required
- core/storage.py: get_engine, get_session, _alembic_config, get_django_engine,
  get_client_by_key_hash, detect_project_id, get_or_create_project
- core/db_init.py: core_schema_status, initialize_database
- core/migrations/__init__.py: include_name (already supports one shared DB)
- mcp_server/auth_middleware.py: _http_headers, resolve_api_key
- mcp_server/server.py: setup_tools
- Test patterns: tests/test_db_path.py, tests/test_mcp_auth.py, tests/conftest.py

## 5. Environment notes

- The local .env already has a working Supabase session-pooler DATABASE_URL.
  Never print it or commit it.
- The unit tests must not need that URL. Use SQLite, and inspect
  engines/dialects for Postgres behavior. Only the final live check uses
  Supabase.
- psycopg is already installed in .venv. uv is at ~/Library/Python/3.9/bin/uv
  (not on PATH) if you need to sync dependencies after editing pyproject.toml.
- Commit messages follow .claude/commit_template.txt. Do NOT add any
  Co-Authored-By or Claude attribution line.

## 6. Implementation rules

- Follow the spec's checklist in order.
- Do not break existing behavior; all existing tests must still pass.
- Do not add scope beyond the spec. Its "Out of scope" list is binding.
- If the spec is ambiguous or conflicts with docs/CLAUDE.md, stop and ask.

## 7. Before you finish

- Run `pytest` and `cd api && python manage.py test`.
- Run `fastmcp inspect server.py:mcp` and confirm 5 tools plus the instructions.
- Do the live Supabase check in the spec's checklist, if the developer agrees.
  It creates real tables and rows.
- Confirm the local stdio MCP still works.
- Report:
  - what you built;
  - any deviation from the spec and why;
  - what's left undone;
  - the exact deploy steps the developer still has to do.

Start by reading docs/CLAUDE.md, then the spec, then ADR 026, then begin.
```
