# Coding Agent Prompt: Agent REST API

**Status:** ✅ Completed — kept for reference
**Updated:** 2026-09-27 (as built; client naming per ADR 025)

---

This task is done. The prompt below is what a coding session would be given to build it; it's kept so future prompts can follow the same shape. See `docs/spec/SPEC_AGENT_REST_API.md` for what was actually built.

---

## Your task

Expose the five MCP tools over HTTP at `/api/agent/v1/context/`, for callers that can't speak MCP (webhooks, serverless, CI, scripts).

The caller is a **client**: anything holding an API key (ADR 025). REST uses the same client key, authorization and audit path as MCP.

## What already exists — reuse it

- `core/auth.py` — `authenticate_client()`, `run_as_client()` (authorize + run + audit in one call)
- `core/services.py` — `get_briefing`, `log_decision`, `update_state`, `log_session`, `export_markdown`
- `api/clients/` — `Client`, `ApiKey`, `create_client()`, `ClientKeyAuthentication`
- `mcp_server/auth_middleware.py` — how the MCP transport does the same thing

## What to build

1. `api/context/serializers.py` — request shapes for the 5 endpoints.
2. `api/context/views.py` — one view per endpoint. Each validates input and makes exactly one `core.services` call through `run_as_client`. Map errors: auth → 401, wrong project → 403, validation → 400, anything else → 500 with a generic message.
3. `api/context/urls.py` + mount at `api/agent/v1/context/` in `api/api/urls.py`.
4. `api/context/tests.py` — valid/invalid/missing key, wrong project, all 5 endpoints, audit rows written.

## Rules

- No business logic in views; Django writes context only through `core.services` (`docs/CLAUDE.md` rule 4).
- Audit `tool_name` values must match the MCP tool names.
- MCP must keep working and must not depend on Django.
- Don't echo internal errors to the client.

## Done when

- All 5 endpoints work with a client key.
- 401 / 403 / 400 / 500 behave as above.
- Every call writes an audit row.
- pytest and Django test suites both pass.
