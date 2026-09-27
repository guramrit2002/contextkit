# ADR 024 — API separation by consumption pattern

**Status:** Proposed

## Context

Step 2 (hosted) has three distinct consumers calling the backend:

1. **Users** (humans via browser/CLI) — manage agents, view audits, settings
2. **Platform** (internal Django services) — compaction, analytics, summarization
3. **Agents** (AI over network via MCP) — record context, retrieve briefings

Each has different:
- Authentication model (session vs. service secret vs. API key)
- Performance requirements (interactive vs. batch vs. low-latency)
- Rate limiting strategy (per-user vs. unlimited vs. per-agent)
- Documentation and versioning approach

A single monolithic API endpoint would force compromises. Separation clarifies intent and improves security.

## Decision

### API tiers

#### Tier 1: User APIs (Django REST)

**Endpoint:** `/api/v1/`  
**Transport:** HTTPS (user-facing)  
**Auth:** Django session + JWT (mobile)  
**Rate limit:** Per user (e.g., 100 req/min)  
**Contract:** Versioned (`/v1/`, `/v2/` in future)  
**Docs:** Public OpenAPI/Swagger  
**Latency:** ~200ms (UI-friendly)

**Purpose:** Humans manage agents, projects, credentials, audit trails.

**Endpoints:**
```
POST   /api/v1/agents/
GET    /api/v1/agents/
GET    /api/v1/agents/{id}/
DELETE /api/v1/agents/{id}/
POST   /api/v1/agents/{id}/keys/rotate/
GET    /api/v1/agents/{id}/audit-log/

GET    /api/v1/projects/
GET    /api/v1/projects/{id}/
GET    /api/v1/projects/{id}/briefing/
GET    /api/v1/projects/{id}/decisions/
GET    /api/v1/projects/{id}/sessions/

GET    /api/v1/audit-log/
POST   /api/v1/audit-log/export/
```

#### Tier 2: Platform APIs (Django Internal)

**Endpoint:** `/api/internal/`  
**Transport:** HTTPS (internal network only)  
**Auth:** Service secret (environment variable)  
**Rate limit:** Unlimited (internal, trusted)  
**Contract:** Unstable (internal only, no versioning)  
**Docs:** Internal specification  
**Latency:** Variable (batch, async ok)

**Purpose:** Backend services (compaction, analytics, LLM calls, reporting).

**Endpoints:**
```
POST   /api/internal/compaction/run/
GET    /api/internal/compaction/status/

POST   /api/internal/audit/export/
GET    /api/internal/audit/stats/
POST   /api/internal/audit/archive/

POST   /api/internal/summarize/{project_id}/
GET    /api/internal/summarize/{project_id}/status/

GET    /api/internal/health/
GET    /api/internal/metrics/
```

#### Tier 3: MCP APIs (FastMCP)

**Endpoint:** TCP/stdio (local), HTTP (hosted)  
**Transport:** Separate from Django (different process/port)  
**Auth:** API key per agent (from agents table)  
**Rate limit:** Per agent (e.g., 1000 req/min)  
**Contract:** MCP specification (tool schema)  
**Docs:** Tool definitions (auto-generated)  
**Latency:** <100ms (agents wait synchronously)

**Purpose:** Agents retrieve context and record decisions/sessions.

**Tools:**
```
get_context(project_id)
log_decision(project_id, decision, reasoning, alternatives)
update_state(project_id, progress, next_steps, blockers)
log_session(project_id, summary, decisions_made)
export_markdown(project_id, output_path)
```

#### Tier 4: Agent REST APIs (Django REST, API key)

**Endpoint:** `/api/agent/v1/context/`  
**Transport:** HTTPS, served by Django  
**Auth:** Same agent API key as MCP (`Authorization: Bearer <key>`), always required  
**Rate limit:** Deferred (same as MCP)  
**Contract:** Versioned (`/api/agent/v1/`)  
**Latency:** Same target as MCP

**Purpose:** The MCP tools over plain HTTP, for agents and scripts in environments without
MCP support (CI jobs, webhooks, serverless functions, CLIs).

**Endpoints:**
```
GET    /api/agent/v1/context/briefing/     ← get_context
POST   /api/agent/v1/context/decisions/    ← log_decision
POST   /api/agent/v1/context/state/        ← update_state
POST   /api/agent/v1/context/sessions/     ← log_session
POST   /api/agent/v1/context/export/       ← export_markdown
```

**Rules:**
- Separate prefix from User APIs (`/api/v1/`) so the two auth schemes never share a route
  and each tier can be routed, rate-limited, and firewalled independently.
- Views are thin: authenticate with `core.auth`, then one `core.services` call through
  `core.auth.run_as_agent`, which enforces the agent's project and writes the audit row.
  Same checks and same audit trail as MCP; Django never writes context tables itself.
- Unlike MCP over stdio, there is no keyless local mode: a missing key is always 401.
- Errors: 401 missing/invalid key, 403 other project, 400 invalid input, 500 otherwise
  (details stay in the audit log, never in the response).

---

## URL Structure

```
contextkit/
├── /api/v1/                        ← User APIs (Django REST)
│   ├── agents/
│   ├── projects/
│   ├── audit-log/
│   └── ...
├── /api/internal/                  ← Platform APIs (Django internal)
│   ├── compaction/
│   ├── audit/
│   ├── summarize/
│   └── health/
├── /api/agent/v1/context/          ← Agent REST APIs (Django, agent API key)
│   ├── briefing/  decisions/  state/
│   └── sessions/  export/
├── /mcp                            ← MCP server (FastMCP)
│   └── (stdio or HTTP stream)
└── /admin/                         ← Django admin (not exposed publicly)
```

---

## Authentication Model

### User APIs (`/api/v1/`)

**Web browser:**
```
GET /api/v1/agents/
Headers: Cookie: sessionid=...
→ Django session middleware validates
```

**Mobile/CLI:**
```
POST /api/v1/login/
Body: { "email": "user@example.com", "password": "..." }
Response: { "token": "eyJ..." }

GET /api/v1/agents/
Headers: Authorization: Bearer eyJ...
→ JWT middleware validates
```

**Implementation:**
```python
# backend/auth.py
class JWTAuthentication:
    """Token-based auth for mobile/CLI."""
    def authenticate(self, request):
        token = request.META.get('HTTP_AUTHORIZATION', '').split(' ')
        if len(token) != 2 or token[0] != 'Bearer':
            return None
        
        user = self.validate_jwt(token[1])
        return (user, None)
```

### Platform APIs (`/api/internal/`)

**Service-to-service:**
```
POST /api/internal/compaction/run/
Headers: Authorization: Bearer SERVICE_SECRET
Body: { "trigger": "manual" }
→ Django REST framework checks SERVICE_SECRET from env
```

**Implementation:**
```python
# backend/auth.py
SERVICE_SECRET = os.environ.get('CONTEXTKIT_SERVICE_SECRET')

class ServiceAuthentication:
    """Service-to-service auth using shared secret."""
    def authenticate(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', '').split(' ')
        if len(auth) != 2 or auth[0] != 'Bearer':
            raise AuthenticationFailed("Missing service secret")
        
        if auth[1] != SERVICE_SECRET:
            raise AuthenticationFailed("Invalid service secret")
        
        return (ServiceUser(), None)
```

### MCP APIs (MCP server)

**Agent request (via stdio or HTTP):**
```
Tool: get_context
Input: { "project_id": "proj-1" }
Header: Authorization: Bearer <API_KEY>
→ MCP server middleware calls authenticate_agent()
```

**Already defined in ADR 022.**

---

## Rate Limiting Strategy

### User APIs

```python
# backend/throttling.py
class UserRateThrottle(SimpleRateThrottle):
    scope = 'user_api'
    # 100 requests per minute per user
    rate = '100/min'

class UserViewSet(ViewSet):
    throttle_classes = [UserRateThrottle]
```

**Per-endpoint limits:**
- Read (GET): 100/min
- Write (POST/PUT): 50/min
- Heavy (export, summarize): 5/min

### Platform APIs

```python
class InternalRateThrottle(SimpleRateThrottle):
    scope = 'internal'
    # No limit (internal, trusted)
    rate = None
```

### MCP APIs

```python
# mcp_server/throttling.py
async def check_rate_limit(agent_id: str):
    """Check if agent has exceeded rate limit (1000/min)."""
    redis_key = f"mcp:rate:{agent_id}"
    count = await redis.incr(redis_key)
    
    if count == 1:
        await redis.expire(redis_key, 60)  # 1-minute window
    
    if count > 1000:
        raise RateLimitExceeded(f"Agent {agent_id} rate limit exceeded")
```

---

## Versioning Strategy

### User APIs: Semantic Versioning

**URL:** `/api/v1/`, `/api/v2/`, etc.

**Policy:**
- Breaking changes → new major version
- Non-breaking additions → same version
- Old versions supported for 12 months

**Example: Rotating from v1 to v2**
```python
# backend/urls.py
urlpatterns = [
    path('api/v1/', include('api.v1.urls')),
    path('api/v2/', include('api.v2.urls')),
]
```

### Platform APIs: Internal (No Versioning)

**URL:** `/api/internal/` (always latest)

**Policy:**
- Backward incompatible changes allowed
- Only used by code we control
- Deprecate with 30-day notice

### MCP APIs: MCP Specification

**No versioning:** MCP tools are part of the protocol spec.

**Policy:**
- Tool signature changes → new tool name (e.g., `get_context_v2`)
- Tool retirement → deprecation notice in schema

---

## Security: API Isolation

### Network

```
┌──────────────────────────────────┐
│ Internet                         │
├──────────────────────────────────┤
│ [Users] ──HTTPS──→ /api/v1/      │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│ Internal Network                 │
├──────────────────────────────────┤
│ [Services] ──HTTPS──→ /api/internal/
└──────────────────────────────────┘

┌──────────────────────────────────┐
│ MCP Clients (agents)             │
├──────────────────────────────────┤
│ [Agents] ──HTTP(S)──→ /mcp       │
└──────────────────────────────────┘
```

### Access Control

| API Tier | Who can call | How to identify | Enforce |
|---|---|---|---|
| User | Any authenticated user | JWT/session | User owns resource |
| Platform | Only backend services | SERVICE_SECRET | Service identity |
| MCP | Only agents | API key | Agent assigned to project |
| Agent REST | Only agents (non-MCP) | API key | Agent assigned to project |

---

## Examples: Request/Response Flows

### User API: Get audit log

```
User clicks "View Audit Log" in web UI

GET /api/v1/projects/proj-123/audit-log/?limit=50
Headers: Authorization: Bearer eyJ...

Response:
{
  "results": [
    {
      "id": "event-1",
      "agent_id": "agent-abc",
      "tool_name": "log_decision",
      "timestamp": "2026-09-27T10:30:00Z",
      "status": "success"
    }
  ],
  "count": 150,
  "next": "...?offset=50"
}
```

### Platform API: Trigger compaction

```
Scheduled job (12 AM) calls:

POST /api/internal/compaction/run/
Headers: Authorization: Bearer <SERVICE_SECRET>
Body: { "trigger": "scheduled", "max_age_days": 30 }

Response:
{
  "status": "started",
  "job_id": "compaction-abc123",
  "estimated_duration_seconds": 60
}
```

### MCP API: Log decision

```
Agent calls MCP tool:

Tool: log_decision
Input: {
  "project_id": "proj-123",
  "decision": "Use async workers",
  "reasoning": "Better throughput for background jobs",
  "alternatives_considered": "sync queue"
}
Header: Authorization: Bearer <AGENT_API_KEY>

Response:
{
  "success": true,
  "decision_id": "dec-xyz789"
}
```

---

## Implementation Roadmap

### Phase 1: Separate endpoints

- [ ] Create `/api/v1/` (Django REST, Django session auth)
- [ ] Create `/api/internal/` (Django REST, service secret auth)
- [ ] Keep existing `/mcp` (FastMCP, API key auth from ADR 022)

### Phase 2: Rate limiting

- [ ] Add throttle classes to User APIs
- [ ] Add rate limit checks to MCP server
- [ ] Monitor and tune limits

### Phase 3: Documentation

- [ ] Generate OpenAPI spec for `/api/v1/`
- [ ] Write internal spec for `/api/internal/`
- [ ] Document MCP tools in schema

### Phase 4: Client SDKs

- [ ] Python SDK for User APIs
- [ ] JavaScript SDK for User APIs
- [ ] MCP already integrated in Anthropic SDK

---

## Consequences

✅ **Clear separation of concerns:**
- User APIs focused on UI/CLI workflows
- Platform APIs focused on backend operations
- MCP APIs focused on agent-to-server communication

✅ **Better security:**
- Each tier has appropriate auth model
- Tier 2 (internal) not exposed to internet
- Tier 3 (MCP) can be rate-limited per agent

✅ **Easier to scale:**
- User API can scale independently (maybe CDN, caching)
- Platform API can be background jobs (no latency constraint)
- MCP API optimized for low-latency (dedicated process/port)

✅ **Clear versioning:**
- User APIs versioned (backward compat)
- Platform APIs internal (no compat guarantee)
- MCP APIs standardized (MCP spec)

⚠️ **More endpoints to maintain:**
- Three URL namespaces instead of one
- More documentation to keep in sync
- Deployment complexity (separate services eventually)

---

## Deferred

1. **Caching strategy** — where to cache User API responses (Redis, CDN)
2. **Webhook APIs** — should platform send webhooks on audit events?
3. **GraphQL option** — alternative to REST for User APIs
4. **Admin APIs** — separate tier for admin-only operations?

---

## Open questions

1. Should `/api/internal/` be accessible only from internal network (firewall), or relying on SERVICE_SECRET is enough?
2. Should we implement circuit breakers on Platform API calls to prevent cascading failures?
3. Should User API support GraphQL in addition to REST for better client ergonomics?
4. Should MCP server run in the same Django process, or separate (for better isolation)?

---

## Related ADRs

- ADR 022: Agent authentication (MCP API auth)
- ADR 023: Agent data flow (how MCP requests flow)
- ADR 003: Django backend (User + Platform APIs)
- ADR 001: MCP server (MCP API)
