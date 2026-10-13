# Project Status

**Updated:** 2026-09-28
**Branch:** `dev` (up to date with `origin/dev`, `531d052`)
**Tests:** 160 pytest (95% coverage) + 48 Django — all passing

---

## Done

### Client authentication (ADR 020, 022, 023, 025)
- API keys issued by Django (`api/clients/`), stored as SHA-256 hashes only (`ck_` prefix).
- One client per project. A client is anything holding an API key: an AI agent over MCP, or a script/webhook/CI job over REST (ADR 025).
- `core/auth.py`: `authenticate_client()`, `validate_client_project_access()`, `run_as_client()` — the single guarded path that authorizes, runs the service call, and writes the audit row.
- Audit log (`audit_log`) records every call: client, tool, project, status, duration. Error messages are redacted before storage.
- Core reads Django's `clients`/`api_keys` tables through a read-only connection; it never writes them.

### MCP transport
- All 5 tools (`get_context`, `log_decision`, `update_state`, `log_session`, `export_markdown`) authenticate via API key.
- Local mode still works without a key unless `REQUIRE_AUTH` is set.
- Registered locally in Claude Code (local scope) with the project venv and a client key.

### Agent REST API — Tier 2 (ADR 024)
- `/api/agent/v1/context/` mirrors the 5 MCP tools for environments without MCP.
- Same API key, same authorization, same audit trail as MCP (via `run_as_client`).
- Postman collection: `docs/postman/contextkit-agent-rest-api.postman_collection.json`.

### Databases (ADR 008)
- Renamed to `core.sqlite3` (Alembic, head `0003`) and `api/django.sqlite3` (Django). Committed in `f95b077`.
- Context rebuilt after the old core file was deleted outside the design session: 9 decisions, 8 sessions, current state. Audit rows before 2026-09-28 were lost.

### Secret redaction (ADR 017)
- Phase 1 regex redaction runs before storage. `detect-secrets` deferred to phase 2.

---

## In progress

### Horizon deployment (ADR 026) — spec ready
- Spec: `docs/spec/SPEC_HORIZON_DEPLOY.md`. Coding prompt: `docs/prompts/PROMPT_HORIZON_DEPLOY.md`.
- The MCP server goes on Prefect Horizon, backed by one Supabase Postgres, with Horizon auth off and our API keys only.
- Supabase is set up: session pooler, Tokyo region, Postgres 17.6, UTC, SSL. It's reachable from local `.env` and has no tables yet. `psycopg` is installed in the venv.
- Still to do in Supabase: disable the Data API, and add `?sslmode=require` to `DATABASE_URL`.

### Uncommitted on `dev`
- `api/api/settings.py`: `DEBUG` parsed as a real boolean, `ALLOWED_HOSTS` split into a list. This fixes Django startup after `67dda71`.
- `.gitignore`: ignore `docs/spec/` and `docs/prompts/`.
- Local `.env` (not tracked): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`.

---

## Not started

| Item | Tier / ADR | Notes |
|---|---|---|
| Per-user keys + project-ID normalization | ADR 012, 022 | One key for all repos; the project is sent per call and normalized |
| Hosting Django (sign-up, key UI) | ADR 024, 026 | Needed for self-serve onboarding |
| User APIs (`/api/v1/`) | ADR 024 | Client CRUD, key rotation, audit log viewing |
| Platform internal APIs (`/api/internal/`) | ADR 024 | Compaction, audit export, summarization |
| Key rotation / revocation | ADR 022 (deferred) | |
| Rate limiting | ADR 022, 024 (deferred) | Per client on MCP and REST |
| Row Level Security on Supabase | ADR 026 (deferred) | Defense in depth after the Data API is off |
| `detect-secrets` redaction | ADR 017 phase 2 | More important now that data is hosted |

---

## Open decisions

- Does Horizon forward the `Authorization` header when its auth is off? (ADR 026 — confirm on a preview deploy)
- Where will Django be hosted? (ADR 026)
- Project entity with git remotes as aliases, superseding ADR 012?
- Rename `/api/agent/v1/` → `/api/client/v1/`? (ADR 025, deferred)
- Should `/api/internal/` be network-restricted, or is the service secret enough? (ADR 024)

---

## Key docs

- Rules: `docs/CLAUDE.md`
- Decisions: `docs/adr/` (latest: 026)
- Specs / coding prompts (gitignored): `docs/spec/`, `docs/prompts/`
