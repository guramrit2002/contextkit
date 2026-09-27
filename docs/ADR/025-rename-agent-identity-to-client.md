# ADR 025 — Rename the API key identity from "agent" to "client"

**Status:** Accepted

**Amends:** ADR 020, ADR 022, ADR 023, ADR 024

## Context

ADR 022 introduced an `agents` table: one row per API key holder, assigned to exactly one project. At the time, the only caller was an AI agent speaking MCP, so "agent" was accurate.

ADR 024 then added the agent REST API (`/api/agent/v1/`) for environments without MCP. It authenticates with the same API key and resolves to the same row. The caller behind that key can now be a webhook, a CI job, a script, or a serverless function, none of which is an AI agent.

This creates two problems:

1. **The name is wrong.** The row identifies whoever holds an API key, not what kind of software holds it. The auth layer does not know, and should not care, whether the caller is an AI.
2. **"Agent" means two things.** The product uses "agent" for the AI coding tools it serves (Claude Code, Codex, Cursor). The auth layer uses it for a credential holder. Readers of code and docs have to work out which one is meant.

The rename is cheapest now: the REST API work is still on `feature/agent-rest-api`, and nothing downstream (user APIs, platform APIs, analytics) has been built on the `agent_id` name yet.

## Decision

The API key identity is called a **client**. A client is anything that holds an API key and calls contextkit over any transport (MCP or REST). It is assigned to exactly one project, as before.

"Agent" stays as a product term for AI coding tools. It no longer names anything in the auth layer or the schema.

### Naming map

| Area | Before | After |
|---|---|---|
| Django app | `api/agents/` | `api/clients/` |
| Django model / table | `Agent` / `agents` | `Client` / `clients` |
| API key FK | `ApiKey.agent` / `api_keys.agent_id` | `ApiKey.client` / `api_keys.client_id` |
| Core context columns | `decisions.agent_id`, `sessions.agent_id` | `decisions.client_id`, `sessions.client_id` |
| Audit column | `audit_log.agent_id` | `audit_log.client_id` |
| Core auth | `AgentContext`, `authenticate_agent()`, `current_agent()`, `validate_agent_project_access()`, `run_as_agent()` | `ClientContext`, `authenticate_client()`, `current_client()`, `validate_client_project_access()`, `run_as_client()` |
| Storage | `get_agent_by_key_hash()` | `get_client_by_key_hash()` |
| DRF auth class | `AgentKeyAuthentication` | `ClientKeyAuthentication` |
| Request attribute | `request.agent_context` | `request.client_context` |
| Management command | `create_agent` | `create_client` |
| Index | `ix_audit_log_agent_id_timestamp` | `ix_audit_log_client_id_timestamp` |

### What does not change

- **The REST URL prefix `/api/agent/v1/`.** It names the audience of the API (the agent-facing tier from ADR 024), not the identity table. Renaming it would break clients for no gain.
- **MCP tool names and inputs.** No tool exposes `agent_id` today.
- **API key format (`ck_` prefix), hashing (SHA-256), and the one-client-one-project rule.**
- **Audit `tool_name` values** (`get_context`, `log_decision`, ...).

### Migrations

The two databases are migrated separately, as ADR 008 requires:

- **Django DB** (`clients`, `api_keys`): a Django migration renames the app's table and FK column. Because the app itself is renamed, the migration must preserve existing rows rather than drop and recreate. Existing API keys must keep working after the migration.
- **Core DB** (`decisions`, `sessions`, `audit_log`): an Alembic migration renames `agent_id` to `client_id` on all three tables and renames the audit index. SQLite column renames go through Alembic batch mode.

The read-only SQLAlchemy mappings of the Django tables in `core/models.py` are updated in the same change, so core and Django never disagree on table or column names.

### Naming collision

`Client` shares a name with `django.test.Client` and DRF's `APIClient`. Test modules that need both import the test client under an alias (for example `from django.test import Client as HttpClient`). This is a convention, not a code change.

## Consequences

- The auth layer describes what it actually does: identify an API key holder, independent of transport or caller type.
- "Agent" has one meaning across the project: an AI coding tool.
- Future transports (webhooks, CLI) fit the model without another rename.
- The change touches many files at once: both apps' models, two migrations, core auth and storage, MCP middleware, REST views, tests, docs, and the Postman collection. It must land as one change so no intermediate state has mixed names.
- Existing local databases need both migrations run. Existing API keys must survive.
- ADRs 020, 022, 023 and 024 keep their original text as a historical record. Where they say "agent" in the identity sense, this ADR governs.

## Open questions

- Should `/api/agent/v1/` eventually become `/api/client/v1/` for consistency, with the old prefix kept as an alias? Deferred; no current reason to break callers.
- Should a client carry a `kind` field (`mcp`, `rest`, `ci`, ...) for analytics? Deferred; the audit log already records which tool was called.
