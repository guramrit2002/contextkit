# Implementation Spec: Agent REST API

**Created:** 2026-09-27
**Updated:** 2026-09-27 (as built; client naming per ADR 025)
**Status:** ✅ Completed
**Tier:** Agent-facing REST (ADR 024)
**Context:** ADR 024, 025

---

## Overview

The five MCP tools, exposed over HTTP for callers that can't speak MCP (webhooks, serverless, CI, scripts).

"Agent" in the name refers to the API's audience (the agent-facing tier from ADR 024), not to the identity table. The caller is a **client** (ADR 025).

**Prefix:** `/api/agent/v1/context/`
**Auth:** `Authorization: Bearer <API_KEY>` — the same client key used for MCP
**Authorization, audit:** identical to MCP, through `core.auth.run_as_client`

---

## Endpoints

| Method | Path | Body / query | Success |
|---|---|---|---|
| GET | `briefing/` | `?project_id=` (optional) | 200 — the briefing |
| POST | `decisions/` | `project_id?`, `decision`, `reasoning`, `alternatives_considered?` | 201 — `success`, `decision_id`, `created_at` |
| POST | `state/` | `project_id?`, `progress`, `next_steps`, `blockers?` | 200 — `success`, `updated_at` |
| POST | `sessions/` | `project_id?`, `summary`, `decisions_made?` | 201 — `success`, `session_id`, `created_at` |
| POST | `export/` | `project_id?`, `format` (`markdown`) | 200 — `success`, `format`, `content`, `size_bytes` |

An omitted `project_id` means the client's assigned project.

### Errors
| Status | When |
|---|---|
| 400 | Invalid body/query, or core validation error |
| 401 | Missing or invalid API key |
| 403 | `project_id` is not the client's assigned project |
| 500 | Service failure — generic message; details go to the audit log and server log, never the response |

---

## As built

| File | Role |
|---|---|
| `api/api/urls.py` | Mounts `context.urls` at `api/agent/v1/context/` |
| `api/context/urls.py` | The 5 routes |
| `api/context/serializers.py` | `BriefingQuery`, `LogDecisionRequest`, `UpdateStateRequest`, `LogSessionRequest`, `ExportRequest` |
| `api/context/views.py` | `AgentContextView` base + 5 views. Each validates input and makes **one** `core.services` call through `run_as_client` |
| `api/clients/authentication.py` | `ClientKeyAuthentication` — sets `request.client_context` |
| `api/context/tests.py` | Django tests: auth, 403 on wrong project, all 5 endpoints, audit rows |
| `docs/postman/contextkit-agent-rest-api.postman_collection.json` | Manual testing |

### Request flow
```
Bearer key → ClientKeyAuthentication → core.auth.authenticate_client
          → view validates body → run_as_client(tool, client, project_id, op)
          → authorize project → core.services.<op> → audit row → response
```

---

## Rules this implementation relies on

- Views hold no business logic; they validate shape and forward (`docs/CLAUDE.md` rules 2, 4, 6).
- Django writes context only through `core.services`, never directly.
- Audit `tool_name` values match MCP (`get_context`, `log_decision`, `update_state`, `log_session`, `export_markdown`), so MCP and REST calls are comparable in the audit log.
- MCP never depends on Django being up.

---

## Deferred

- Rate limiting per client
- OpenAPI/Swagger docs
- Renaming the prefix to `/api/client/v1/` (ADR 025 open question — would break callers)
