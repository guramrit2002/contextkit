# Implementation Spec: Client Authentication & Audit

**Created:** 2026-09-27
**Updated:** 2026-09-27 (renamed agent → client, ADR 025)
**Status:** ✅ Completed
**Context:** ADR 020, 022, 023, 025

---

## Overview

API key authentication, one-project authorization, and audit logging for every call into contextkit.

A **client** is anything that holds an API key: an AI agent over MCP, or a script, webhook or CI job over REST. The auth layer doesn't know or care which (ADR 025).

---

## As built

### Django — `api/clients/` (sole writer of these tables)
| Item | Detail |
|---|---|
| `Client` model → `clients` table | `id`, `user_id`, `project_id`, `name`, timestamps. Unique on `(user_id, project_id)`. |
| `ApiKey` model → `api_keys` table | `id`, `client_id` (one-to-one), `key_hash` (SHA-256, unique), `created_at`. |
| `services.py` | `create_client()`, `issue_api_key()`, `generate_api_key()` (`ck_` prefix), `hash_api_key()` |
| `authentication.py` | `ClientKeyAuthentication` (DRF) — reads `Authorization: Bearer <key>` |
| Management command | `python manage.py create_client` |
| Migration | `0001_initial.py` creates the tables; on a DB that had the old `agents` app it carries rows over, so existing keys keep working |

### Core — `core/`
| Item | Detail |
|---|---|
| `auth.py` | `ClientContext`, `authenticate_client()`, `validate_client_project_access()`, `current_client()`, `guarded_call()`, `run_as_client()` |
| `audit.py` | `log_audit_event()` — synchronous, one row per call |
| `storage.py` | `get_client_by_key_hash()` over a **read-only** connection to Django's DB |
| `config.py` | `resolve_db_path()` (core DB), `resolve_django_db_path()` (Django DB) — relative paths resolve from repo root |
| Alembic `0003_rename_agent_to_client.py` | `agent_id` → `client_id` on `decisions`, `sessions`, `audit_log`; reversible |

### Transports
- **MCP** (`mcp_server/auth_middleware.py`): every tool authenticates, then runs through `guarded_call`.
- **REST** (`api/context/views.py`): see `SPEC_AGENT_REST_API.md`. Runs through `run_as_client`.

---

## Rules this implementation relies on

- Only the key hash is stored. The plaintext key is shown once, at creation.
- `core.auth.hash_api_key` and `api/clients/services.hash_api_key` must stay identical.
- Core never writes `clients` or `api_keys`; it opens Django's DB with `mode=ro`.
- No key + `REQUIRE_AUTH` unset → local single-user mode (no client, no audit). No key + `REQUIRE_AUTH` set → denied and audited.
- A client can only act on its assigned project. An omitted `project_id` means the assigned one.

---

## Deferred

- Key rotation / revocation (Django endpoint + UI)
- Rate limiting per client
- Audit log retention
- `detect-secrets` redaction (ADR 017 phase 2)
- TLS enforcement (deployment)
