# ADR 023 — Agent data flow and access control

**Status:** Proposed

## Context

ADR 022 establishes agent authentication. This ADR specifies how agent identity flows through the system, where it's stored, and how access control is enforced at each layer.

## Decision

### Data flow: request → services → storage

```
1. Request arrives at MCP server
   ├─ Extract API key from header
   ├─ Call services.authenticate_agent(key) → (agent_id, user_id, project_id)
   └─ If auth fails → return 401, log audit_log with status=denied

2. MCP tool wrapper receives (agent_id, user_id, project_id)
   ├─ Pass to core service function
   └─ Log to audit_log with request metadata

3. Core service function
   ├─ Receives (agent_id, user_id, project_id)
   ├─ Validate project_id matches agent's assigned project (fail if not)
   ├─ Call storage layer with (user_id, project_id)
   ├─ Redact secrets before storage
   └─ Attach agent_id to records (decisions, sessions)

4. Storage layer
   ├─ Filter all queries by (user_id, project_id)
   ├─ Store agent_id in decisions/sessions for audit
   └─ Write audit_log entry with (agent_id, tool_name, status)
```

### Where agent_id is stored

| Table | Column | Purpose |
|---|---|---|
| `decisions` | `agent_id` (NEW) | Track which agent recorded the decision |
| `sessions` | `agent_id` (NEW) | Track which agent logged the session |
| `audit_log` | `agent_id` (PK) | Central audit trail |

**Note:** `projects`, `state`, and `users` do NOT have `agent_id`. They belong to the project/user level, not agent level.

### Access control at each layer

#### MCP Server (transport layer)
- Validate API key → authenticate_agent()
- If key invalid, return 401 (don't proceed)
- If key valid, extract (agent_id, user_id, project_id)
- Reject if agent_id.project_id ≠ request.project_id (agents can't change their project)

#### Core Services (business logic layer)
- Receive (agent_id, user_id, project_id) from MCP layer
- Every service function filters by user_id and project_id
- Reject if project_id doesn't match agent's assigned project
- Attach agent_id to created records

#### Storage Layer (data layer)
- All SELECT queries filter by (user_id, project_id)
- INSERT includes agent_id for decisions/sessions
- AUDIT_LOG records every operation for compliance

### Pydantic schemas (input validation)

Tool inputs remain unchanged (project_id is optional, auto-detected):
```python
class LogDecisionInput(BaseModel):
    decision: str
    reasoning: str
    alternatives_considered: str | None = None
    project_id: str | None = None  # Auto-detected if omitted
```

But the MCP wrapper validates that auto-detected project_id matches the agent's assigned project.

### Error handling

| Scenario | Response | Audit Log |
|---|---|---|
| Invalid API key | 401 Unauthorized | status=denied, error="invalid_key" |
| Agent project mismatch | 403 Forbidden | status=denied, error="project_mismatch" |
| Tool execution error | 500 Internal Server Error | status=error, error=exception message |
| Tool success | 200 OK | status=success |

---

## Schema additions

### New columns (Alembic migrations)

```sql
-- Attach agent_id to decisions and sessions for audit trail
ALTER TABLE decisions ADD COLUMN agent_id UUID;
ALTER TABLE sessions ADD COLUMN agent_id UUID;
```

### New table (Django migration)

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL,
    tool_name VARCHAR(50) NOT NULL,
    project_id VARCHAR(500) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL,  -- success, error, denied
    error_message TEXT,
    duration_ms INT,  -- response time
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    INDEX (agent_id, timestamp),
    INDEX (project_id, timestamp),
    INDEX (user_id, timestamp)
);
```

---

## Code structure

### `core/services.py` signature changes

**Before:**
```python
async def get_briefing(project_id: Optional[str] = None) -> dict:
    project_id = project_id or storage.detect_project_id()
    # ...
```

**After:**
```python
async def get_briefing(
    project_id: Optional[str] = None,
    agent_id: Optional[UUID] = None,
    user_id: Optional[str] = None,
) -> dict:
    project_id = project_id or storage.detect_project_id()
    # Validate agent is assigned to this project
    if agent_id and user_id:
        await storage.validate_agent_project_access(agent_id, user_id, project_id)
    # ... rest of function
```

### `mcp_server/tools.py` wrapper structure

```python
async def get_context(input: GetContextInput, api_key: str = None) -> dict[str, Any]:
    """Wrapped get_context with auth and audit."""
    from core import services
    
    # 1. Authenticate
    agent_id, user_id, project_id_assigned = services.authenticate_agent(api_key)
    
    # 2. Validate project matches
    project_id = input.project_id or storage.detect_project_id()
    if project_id != project_id_assigned:
        await storage.log_audit_event(
            agent_id=agent_id,
            tool_name="get_context",
            project_id=project_id_assigned,  # log what agent is assigned to
            status="denied",
            error_message=f"Agent not assigned to project {project_id}"
        )
        raise PermissionError("Agent not authorized for this project")
    
    # 3. Call service with auth context
    try:
        briefing = await services.get_briefing(
            project_id=project_id,
            agent_id=agent_id,
            user_id=user_id
        )
        await storage.log_audit_event(
            agent_id=agent_id,
            tool_name="get_context",
            project_id=project_id,
            status="success"
        )
        return briefing
    except Exception as e:
        await storage.log_audit_event(
            agent_id=agent_id,
            tool_name="get_context",
            project_id=project_id,
            status="error",
            error_message=str(e)
        )
        raise
```

---

## Consequences

- ✅ Every tool call is auditable (who, what, when)
- ✅ Data isolation is enforced at multiple layers (defense in depth)
- ✅ Agent identity is preserved in records for future correlation
- ✅ Agents cannot escalate privileges or access other projects
- ✅ Core services remain logic-focused; auth is validated before passing control
- ⏸️ Agent_id is optional in Phase 1 (local mode); required in Phase 2 (hosted)

## Deferred

1. **Audit log retention policies** — how long to keep logs, archival strategy
2. **Audit log export/analytics** — tools to query and visualize audit trails
3. **Agent metadata** — other fields (e.g., api_key rotation schedule, tags)

## Open questions

- Should service functions reject if agent_id is None? (Or allow for backward compatibility with local mode?)
- Should audit_log include request size or other metrics?
- Should agents see their own audit logs via get_context?
