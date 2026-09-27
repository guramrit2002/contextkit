# ADR 022 — Agent authentication and authorization

**Status:** Proposed

## Context

Step 2 moves from local single-user to multi-agent over network. Agents call the MCP server over HTTP, carrying context with database credentials, API keys, and tokens. The system must:
- Identify which agent is making each request
- Enforce data isolation: agents only access their assigned project
- Audit all tool calls for compliance and debugging
- Block unauthorized access immediately

ADR 020 proposed API key authentication. This ADR refines that into a concrete agent identity and authorization model.

## Decision

### Authentication

1. **API keys** identify agents. Django issues a key during agent onboarding, shows it once to the user.
2. Only the **hash** of the key is stored in `api_keys` table. Lookup: incoming key → hash → row → agent_id.
3. The MCP server validates the key on every request by hashing the incoming value and querying the database.

### Agent identity

1. Each agent has a row in the `agents` table:
   - `id` (UUID)
   - `name` (string, user-friendly)
   - `user_id` (who owns it, from Django)
   - `project_id` (the ONE project this agent can access)
   - `created_at`, `updated_at`, `api_key_hash` (reference to api_keys table)

2. Django is the sole writer of `agents` and `api_keys` tables. MCP server only reads.

### Authorization

1. When an agent makes a request:
   - Extract and hash the API key
   - Query `api_keys` for the hash → get `agent_id`
   - Query `agents` for agent_id → get `(user_id, project_id)`
   - Pass `(agent_id, user_id, project_id)` to core services

2. Core services enforce:
   - All queries filter by `(user_id, project_id)` pair
   - Tools only work on that one project
   - An agent cannot read/write context for other projects

### Mapping

- **1 agent per project** (in step 2)
  - agent_id → project_id is unique
  - One project can have multiple users (via Django), each with their own agents
  - Example: user Alice + project foo = alice-agent-foo; user Bob + project foo = bob-agent-foo

### Audit trail

1. Each tool call is logged to `audit_log`:
   - `id` (UUID)
   - `agent_id` (who made the call)
   - `tool_name` (get_context, log_decision, etc.)
   - `project_id` (which project)
   - `timestamp`
   - `status` (success, error, denied)
   - `error_message` (if denied or error)

2. Logging is synchronous and happens in the MCP server before returning, so tool calls are always recorded.

## Schema changes

```sql
-- New tables (managed by Django migrations, not Alembic)
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(500) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE (user_id, project_id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL UNIQUE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    tool_name VARCHAR(50) NOT NULL,
    project_id VARCHAR(500) NOT NULL,
    timestamp DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,  -- success, error, denied
    error_message TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    INDEX (agent_id, timestamp),
    INDEX (project_id, timestamp)
);
```

## Code layer changes

### MCP Server (thin wrapper)

In `mcp_server/tools.py`, each tool is wrapped to:
1. Extract API key from request header (e.g., `Authorization: Bearer <key>`)
2. Call `services.authenticate_agent(api_key)` → get `(agent_id, user_id, project_id)`
3. If auth fails, return 401; log to audit_log with status=denied
4. Pass `(agent_id, user_id, project_id)` to the core service
5. Log to audit_log with status=success or error

### Core Services

All existing functions (`get_briefing`, `log_decision`, etc.) receive `(agent_id, user_id, project_id)` and:
1. Enforce `user_id` filter on all queries (already done, ADR 013)
2. Add `agent_id` to decision/session records for audit trail
3. Reject requests if project_id doesn't match the agent's assigned project

New functions:
- `authenticate_agent(api_key: str) → (agent_id: UUID, user_id: str, project_id: str)` — hash key, lookup agent
- `log_audit_event(agent_id, tool_name, project_id, status, error_message)` — write to audit_log

### Core Storage

Add read functions (MCP calls these):
- `get_agent_by_key_hash(key_hash: str) → Agent`
- `log_audit(agent_id, tool_name, project_id, status, error_message) → None`

## Consequences

- ✅ Agents are identified by cryptographic key; spoofing requires the key.
- ✅ Data isolation is enforced at the service layer; agents cannot access other projects.
- ✅ Audit trail records every tool call; operators can debug or investigate.
- ✅ No changes to core context tables; agent_id is added to sessions/decisions as a new column for audit, but storage layer remains stable.
- ✅ Django remains the sole writer of credentials; no shared secrets in environment or config.
- ⏸️ **Key rotation, revocation, and expiration are deferred** to a follow-up ADR (rate limiting too).

## Deferred

1. **Key rotation** — agents can ask Django for a new key; old key is revoked. Scope: Django UI + API endpoint.
2. **Rate limiting** — protect against brute-force auth attempts or tool call DoS. Scope: MCP server middleware or reverse proxy.
3. **TLS enforcement** — network security. Scope: deployment/ops, not MCP code.

## Open questions

- Should agents log into Django to manage their own keys, or does their creator do it?
- Should audit_log retention be configurable (e.g., keep 90 days)?
- Should get_context return the agent_id in the briefing, so the agent knows its identity?
