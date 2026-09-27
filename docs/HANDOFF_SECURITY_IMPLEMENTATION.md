# Handoff: Agent Authentication & Security Implementation

**Date:** 2026-09-27  
**From:** Architecture/Design phase  
**To:** Implementation agent  
**Status:** Ready to build  

---

## What was decided

Three new Architecture Decision Records (ADRs) were created:

1. **ADR 022: Agent Authentication** — How agents prove identity (API keys), 1:1 agent-to-project mapping
2. **ADR 023: Agent Data Flow** — How agent_id flows through the system, where it's stored, access control enforcement
3. **ADR 017 (updated): Secret Redaction** — Two-phase approach: regex now, detect-secrets later

**Files to read for context:**
- `docs/adr/022-agent-authentication.md`
- `docs/adr/023-agent-data-flow.md`
- `docs/adr/017-redaction-approach.md`

---

## What needs to be built

**See:** `docs/IMPLEMENTATION_SPEC_AGENT_AUTH.md` (detailed spec)

**TL;DR:**
- 3 new database tables: agents, api_keys, audit_log
- 2 new Python modules: core/auth.py, core/audit.py
- Update 4 existing modules: core/storage.py, core/services.py, mcp_server/tools.py, mcp_server/server.py
- 2 new migrations: Alembic (core) + Django (backend)
- Tests: unit tests for auth, integration tests for MCP tools

---

## Architecture

```
Request with API key
  ↓
[MCP Server] @require_auth decorator
  ├─ Extract key from header
  ├─ Call authenticate_agent(key)
  ├─ Get (agent_id, user_id, project_id)
  ├─ Validate project access
  └─ Log to audit_log

[Core Services]
  ├─ Receive (agent_id, user_id, project_id)
  ├─ Redact secrets
  ├─ Call storage layer
  └─ Attach agent_id to records

[Storage]
  ├─ Filter by (user_id, project_id)
  ├─ Store agent_id in decisions/sessions
  └─ Write audit_log
```

---

## Key Files to Modify

| File | Change | Complexity |
|---|---|---|
| `core/models.py` | Add agent_id columns to Decision, Session | Low |
| `core/auth.py` | NEW: authenticate_agent(), hash_api_key() | Medium |
| `core/audit.py` | NEW: log_audit_event() | Low |
| `core/storage.py` | Add read functions for auth, create_audit_log_entry() | Medium |
| `core/services.py` | Add (agent_id, user_id) params to all functions | High |
| `mcp_server/auth_middleware.py` | NEW: @require_auth decorator | Medium |
| `mcp_server/tools.py` | Apply @require_auth, add auth params to inputs | High |
| `mcp_server/server.py` | Register authenticated tool versions | Low |
| `core/migrations/versions/001_add_agent_id.py` | Alembic migration | Low |
| `backend/migrations/0001_agents.py` | Django migration | Low |
| `tests/test_auth.py` | NEW: unit tests | Medium |
| `tests/test_mcp_auth.py` | NEW: integration tests | Medium |

---

## Implementation order (recommended)

1. **Database migrations first**
   - Create Alembic migration (add agent_id to decisions, sessions)
   - Create Django migration (new agents, api_keys, audit_log tables)
   - Test migrations run without error

2. **Core services**
   - Implement core/auth.py (authenticate_agent, hash_api_key)
   - Implement core/audit.py (log_audit_event)
   - Add read functions to core/storage.py
   - Update core/services.py (add agent_id, user_id params to all functions)

3. **MCP layer**
   - Implement mcp_server/auth_middleware.py (@require_auth decorator)
   - Update mcp_server/tools.py (apply decorator, add auth params)
   - Update mcp_server/server.py (register authenticated versions)

4. **Tests**
   - Write unit tests (tests/test_auth.py)
   - Write integration tests (tests/test_mcp_auth.py)
   - Verify all tests pass

5. **Verification**
   - Manual test: create an agent, get API key, call a tool
   - Check audit_log for entries
   - Verify data isolation (agent can't access other projects)

---

## Important constraints

- ✅ **No breaking changes.** agent_id is NEW columns (nullable initially).
- ✅ **Core has no framework imports.** Use plain Python in auth.py, audit.py.
- ✅ **MCP is thin.** All logic in core/services. MCP only routes requests.
- ✅ **Backward compatible.** Local mode still works (agent_id=None).
- ✅ **Synchronous audit logging.** Audit entries written before returning.

---

## Success criteria

- [ ] All 5 MCP tools require valid API key
- [ ] Agents can only access their assigned project
- [ ] Every tool call is logged to audit_log
- [ ] Secrets are redacted before storage
- [ ] Tests pass (unit + integration)
- [ ] No data loss or breaking changes

---

## Questions to resolve during implementation

See "Open questions" sections in ADR 022, ADR 023, ADR 017 (updated).

Key ones:
- Should agents see their own audit logs in get_context?
- Should audit_log include request/response size?
- Audit log retention: how long to keep?

---

## Next phase (deferred)

- Key rotation/revocation
- Rate limiting
- Audit log export/analytics
- TLS enforcement

---

## Files to share with implementation agent

1. `docs/adr/022-agent-authentication.md` — authentication design
2. `docs/adr/023-agent-data-flow.md` — data flow and authorization
3. `docs/adr/017-redaction-approach.md` — redaction strategy
4. `docs/IMPLEMENTATION_SPEC_AGENT_AUTH.md` — detailed implementation spec
5. This file (handoff summary)

Good luck! 🚀
