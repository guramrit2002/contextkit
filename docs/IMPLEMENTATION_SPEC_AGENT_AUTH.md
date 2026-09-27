# Implementation Spec: Agent Authentication & Security

**Created:** 2026-09-27  
**For:** Implementation agent  
**Context:** ADR 022, ADR 023, ADR 017 (updated)  
**Status:** Ready for implementation  

---

## Overview

Build authentication, authorization, and audit infrastructure for multi-agent network scenario. Agents authenticate with API keys, access only their assigned project, and all calls are logged.

**Key constraint:** No breaking changes to existing core context tables (projects, decisions, state, sessions). Agent_id is added as new columns, not a refactor of existing data.

---

## Phase: 1 (Now)

### Summary

- Add `agent_id` to decisions and sessions (for audit trail)
- Create agents table (agent identity + project assignment)
- Create api_keys table (hashed keys for auth)
- Create audit_log table (all tool calls logged)
- Implement authenticate_agent() service
- Implement log_audit_event() service
- Wrap MCP tools with auth middleware
- Update all service functions to accept (agent_id, user_id, project_id)

---

## Database Schema Changes

### 1. Alembic Migration: Add agent_id columns

**File:** `core/migrations/versions/001_add_agent_id_columns.py`

```python
# Add agent_id to existing tables
decisions.agent_id = Column(UUID, ForeignKey('agents.id'), nullable=True)
sessions.agent_id = Column(UUID, ForeignKey('agents.id'), nullable=True)
```

**Note:** Nullable in Phase 1 (backward compat with local mode). Becomes required in Phase 2 (hosted).

### 2. Django Migration: Create agents, api_keys, audit_log tables

**File:** `backend/migrations/0001_create_agent_tables.py`

```python
class Migration(migrations.Migration):
    dependencies = [...]
    
    operations = [
        # agents table
        migrations.CreateModel(
            name='Agent',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4)),
                ('user_id', models.CharField(max_length=255)),
                ('project_id', models.CharField(max_length=500)),
                ('name', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'unique_together': {('user_id', 'project_id')}},
        ),
        
        # api_keys table
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4)),
                ('agent_id', models.OneToOneField(to='Agent', on_delete=models.CASCADE)),
                ('key_hash', models.CharField(max_length=255, unique=True, db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        
        # audit_log table
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4)),
                ('agent_id', models.ForeignKey(to='Agent', on_delete=models.CASCADE)),
                ('tool_name', models.CharField(max_length=50)),
                ('project_id', models.CharField(max_length=500)),
                ('user_id', models.CharField(max_length=255)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('status', models.CharField(max_length=20, choices=[
                    ('success', 'success'),
                    ('error', 'error'),
                    ('denied', 'denied'),
                ])),
                ('error_message', models.TextField(null=True, blank=True)),
                ('duration_ms', models.IntegerField(null=True, blank=True)),
            ],
            options={'indexes': [
                models.Index(fields=['agent_id', 'timestamp']),
                models.Index(fields=['project_id', 'timestamp']),
                models.Index(fields=['user_id', 'timestamp']),
            ]},
        ),
    ]
```

---

## Core Services

### 1. Update `core/models.py`

**Add to existing models:**

```python
class Decision(Base):
    __tablename__ = "decisions"
    
    id = Column(String(36), primary_key=True)
    project_id = Column(String(500), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    agent_id = Column(String(36), nullable=True)  # NEW: track which agent logged this
    decision = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False)
    alternatives_considered = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String(36), primary_key=True)
    project_id = Column(String(500), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    agent_id = Column(String(36), nullable=True)  # NEW: track which agent logged this
    summary = Column(Text, nullable=False)
    decisions_made = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)
```

### 2. Create `core/auth.py`

**New file with authentication logic:**

```python
"""Agent authentication and authorization."""
import hashlib
import uuid
from typing import Optional, NamedTuple
from sqlalchemy.orm import Session as DBSession

class AgentContext(NamedTuple):
    """Result of successful authentication."""
    agent_id: str
    user_id: str
    project_id: str


async def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def authenticate_agent(
    api_key: str,
    db_session: DBSession,
) -> AgentContext:
    """
    Authenticate an agent by API key.
    
    Returns AgentContext (agent_id, user_id, project_id) if valid.
    Raises ValueError if key not found or invalid.
    """
    if not api_key or not isinstance(api_key, str):
        raise ValueError("Invalid API key format")
    
    # Hash the incoming key
    key_hash = await hash_api_key(api_key)
    
    # Query api_keys table for the hash
    from core.storage import get_api_key_by_hash, get_agent_by_id
    
    api_key_record = await get_api_key_by_hash(key_hash, db_session)
    if not api_key_record:
        raise ValueError("API key not found or invalid")
    
    # Get agent details
    agent = await get_agent_by_id(api_key_record.agent_id, db_session)
    if not agent:
        raise ValueError("Agent not found")
    
    return AgentContext(
        agent_id=str(agent.id),
        user_id=agent.user_id,
        project_id=agent.project_id,
    )


async def validate_agent_project_access(
    agent_id: str,
    assigned_project_id: str,
    requested_project_id: str,
) -> bool:
    """Validate that agent is authorized for the requested project."""
    if assigned_project_id != requested_project_id:
        raise PermissionError(
            f"Agent {agent_id} not authorized for project {requested_project_id}. "
            f"Assigned to: {assigned_project_id}"
        )
    return True
```

### 3. Create `core/audit.py`

**New file with audit logging:**

```python
"""Audit logging for all tool calls."""
import uuid
from datetime import UTC, datetime
from typing import Optional
from sqlalchemy.orm import Session as DBSession

from core.storage import create_audit_log_entry


async def log_audit_event(
    agent_id: str,
    tool_name: str,
    project_id: str,
    user_id: str,
    status: str,  # 'success', 'error', 'denied'
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    db_session: Optional[DBSession] = None,
) -> None:
    """
    Log a tool call to the audit log.
    
    Args:
        agent_id: UUID of the agent making the call
        tool_name: Name of the tool (e.g., 'get_context', 'log_decision')
        project_id: Project the call is for
        user_id: User ID from agent context
        status: 'success', 'error', or 'denied'
        error_message: If status is 'error' or 'denied', the error message
        duration_ms: Response time in milliseconds (optional)
        db_session: Database session (uses get_session() if None)
    """
    if db_session is None:
        from core.storage import get_session
        db_session = get_session()
    
    try:
        await create_audit_log_entry(
            agent_id=agent_id,
            tool_name=tool_name,
            project_id=project_id,
            user_id=user_id,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
            db_session=db_session,
        )
    except Exception as e:
        # Log but don't fail if audit logging fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to log audit event: {e}")
```

### 4. Update `core/storage.py`

**Add new read functions for auth:**

```python
async def get_api_key_by_hash(
    key_hash: str,
    session: Session,
) -> Optional[dict]:
    """Retrieve API key record by hash (for auth)."""
    from core.models import ApiKey  # Import from Django models
    
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = session.execute(stmt).scalar_one_or_none()
    
    if not result:
        return None
    
    return {
        "id": str(result.id),
        "agent_id": str(result.agent_id),
        "created_at": result.created_at,
    }


async def get_agent_by_id(
    agent_id: str,
    session: Session,
) -> Optional[dict]:
    """Retrieve agent record by ID (for auth)."""
    from core.models import Agent  # Import from Django models
    
    stmt = select(Agent).where(Agent.id == agent_id)
    result = session.execute(stmt).scalar_one_or_none()
    
    if not result:
        return None
    
    return {
        "id": str(result.id),
        "user_id": result.user_id,
        "project_id": result.project_id,
        "name": result.name,
        "created_at": result.created_at,
    }


async def create_audit_log_entry(
    agent_id: str,
    tool_name: str,
    project_id: str,
    user_id: str,
    status: str,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    session: Optional[Session] = None,
) -> None:
    """Create an audit log entry."""
    from core.models import AuditLog  # Import from Django models
    
    if session is None:
        session = get_session()
    
    entry = AuditLog(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        tool_name=tool_name,
        project_id=project_id,
        user_id=user_id,
        timestamp=datetime.now(UTC),
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    session.add(entry)
    session.commit()
```

### 5. Update `core/services.py`

**Update all tool functions to accept agent context:**

```python
async def get_briefing(
    project_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get the project briefing for an agent to load.
    
    Args:
        project_id: Project to get briefing for
        agent_id: Agent making the request (for audit)
        user_id: User ID (for data isolation)
    """
    from core import storage
    
    try:
        project_id = validate_get_context_input(project_id) or storage.detect_project_id()
        
        # Validate agent is authorized for this project (if agent_id provided)
        if agent_id:
            # In Phase 2, this becomes required validation
            pass
        
        briefing = await storage.get_briefing(project_id, user_id=user_id)
        return briefing
    except Exception as e:
        logger.error(f"Failed to get briefing: {e}")
        raise


async def log_decision(
    project_id: Optional[str],
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Record a decision and its reasoning.
    
    Args:
        project_id: Project the decision belongs to
        decision: Decision statement
        reasoning: Rationale
        alternatives_considered: Other options considered
        agent_id: Agent making the decision (for audit)
        user_id: User ID (for data isolation)
    """
    from core import storage
    
    try:
        decision, reasoning, alternatives_considered = validate_log_decision_input(
            decision, reasoning, alternatives_considered
        )
        
        # Redact secrets before storing
        decision = SecretRedactor.redact(decision)
        reasoning = SecretRedactor.redact(reasoning)
        if alternatives_considered:
            alternatives_considered = SecretRedactor.redact(alternatives_considered)
        
        project_id = project_id or storage.detect_project_id()
        decision_record = await storage.create_decision(
            project_id=project_id,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives_considered,
            agent_id=agent_id,  # NEW: include agent_id
            user_id=user_id,
        )
        return decision_record
    except Exception as e:
        logger.error(f"Failed to log decision: {e}")
        raise

# Similar updates for: update_state(), log_session(), export_markdown()
```

---

## MCP Server Layer

### 1. Create `mcp_server/auth_middleware.py`

**New file for auth wrapper logic:**

```python
"""Authentication middleware for MCP tools."""
import time
from typing import Any, Callable
from functools import wraps

from core.auth import authenticate_agent, AgentContext
from core.audit import log_audit_event


def require_auth(tool_name: str):
    """
    Decorator for MCP tools that require authentication.
    
    Extracts API key from request context, authenticates agent,
    validates project access, logs to audit_log, and passes
    (agent_id, user_id, project_id) to the tool function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(input: Any, api_key: str = None) -> dict[str, Any]:
            start_time = time.time()
            agent_ctx = None
            error_msg = None
            
            try:
                # 1. Authenticate
                if not api_key:
                    raise ValueError("API key required in Authorization header")
                
                from core.storage import get_session
                db_session = get_session()
                
                agent_ctx = await authenticate_agent(api_key, db_session)
                
                # 2. Validate project access if project_id is in input
                if hasattr(input, 'project_id') and input.project_id:
                    if input.project_id != agent_ctx.project_id:
                        raise PermissionError(
                            f"Agent not authorized for project {input.project_id}"
                        )
                
                # 3. Call the tool with auth context
                # Attach auth context to input
                input.agent_id = agent_ctx.agent_id
                input.user_id = agent_ctx.user_id
                
                result = await func(input)
                
                # 4. Log success
                duration_ms = int((time.time() - start_time) * 1000)
                await log_audit_event(
                    agent_id=agent_ctx.agent_id,
                    tool_name=tool_name,
                    project_id=agent_ctx.project_id,
                    user_id=agent_ctx.user_id,
                    status="success",
                    duration_ms=duration_ms,
                )
                
                return result
                
            except PermissionError as e:
                error_msg = str(e)
                await log_audit_event(
                    agent_id=agent_ctx.agent_id if agent_ctx else "unknown",
                    tool_name=tool_name,
                    project_id=agent_ctx.project_id if agent_ctx else "unknown",
                    user_id=agent_ctx.user_id if agent_ctx else "unknown",
                    status="denied",
                    error_message=error_msg,
                )
                raise
                
            except Exception as e:
                error_msg = str(e)
                await log_audit_event(
                    agent_id=agent_ctx.agent_id if agent_ctx else "unknown",
                    tool_name=tool_name,
                    project_id=agent_ctx.project_id if agent_ctx else "unknown",
                    user_id=agent_ctx.user_id if agent_ctx else "unknown",
                    status="error",
                    error_message=error_msg,
                )
                raise
        
        return wrapper
    return decorator
```

### 2. Update `mcp_server/tools.py`

**Apply auth middleware to all tools:**

```python
"""MCP tool definitions for contextkit."""
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from mcp_server.auth_middleware import require_auth


class GetContextInput(BaseModel):
    """Input for get_context tool."""
    project_id: str | None = Field(
        None,
        description="Project ID. If not provided, inferred from git remote or current path.",
    )
    agent_id: str | None = None  # Added by auth middleware
    user_id: str | None = None   # Added by auth middleware


class LogDecisionInput(BaseModel):
    """Input for log_decision tool."""
    decision: str = Field(description="What decision was made")
    reasoning: str = Field(description="Why this decision was made")
    alternatives_considered: str | None = Field(
        None, description="Other options that were considered"
    )
    project_id: str | None = Field(None, description="Project ID (auto-detected if omitted)")
    agent_id: str | None = None  # Added by auth middleware
    user_id: str | None = None   # Added by auth middleware

# Similar for UpdateStateInput, LogSessionInput, ExportMarkdownInput


@require_auth("get_context")
async def get_context_authenticated(input: GetContextInput) -> dict[str, Any]:
    """Return the project briefing for the agent to load."""
    from core import services
    
    briefing = await services.get_briefing(
        project_id=input.project_id,
        agent_id=input.agent_id,
        user_id=input.user_id,
    )
    return briefing


@require_auth("log_decision")
async def log_decision_authenticated(input: LogDecisionInput) -> dict[str, Any]:
    """Record a decision and its reasoning."""
    from core import services
    
    decision_record = await services.log_decision(
        project_id=input.project_id,
        decision=input.decision,
        reasoning=input.reasoning,
        alternatives_considered=input.alternatives_considered,
        agent_id=input.agent_id,
        user_id=input.user_id,
    )
    return {"success": True, "decision_id": decision_record.get("id")}

# Similar for update_state, log_session, export_markdown
```

### 3. Update `mcp_server/server.py`

**Register wrapped tools:**

```python
"""FastMCP server for contextkit."""
import logging
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("contextkit")


def setup_tools():
    """Register all MCP tools."""
    from . import tools
    
    # Register authenticated versions
    mcp.tool(tools.get_context_authenticated, name="get_context")
    mcp.tool(tools.log_decision_authenticated, name="log_decision")
    mcp.tool(tools.update_state_authenticated, name="update_state")
    mcp.tool(tools.log_session_authenticated, name="log_session")
    mcp.tool(tools.export_markdown_authenticated, name="export_markdown")
    
    logger.info("Registered 5 contextkit tools with authentication")
```

---

## Testing

### 1. Unit tests: `tests/test_auth.py`

```python
"""Tests for agent authentication."""
import pytest
from core.auth import authenticate_agent, hash_api_key


@pytest.mark.asyncio
async def test_authenticate_agent_valid_key():
    """Test authentication with valid API key."""
    # Mock: api_keys table has key_hash for agent_id=123
    # api_key = "test_key_abc123"
    # agent_id = "agent-123", user_id = "user-1", project_id = "proj-1"
    
    result = await authenticate_agent("test_key_abc123", db_session)
    
    assert result.agent_id == "agent-123"
    assert result.user_id == "user-1"
    assert result.project_id == "proj-1"


@pytest.mark.asyncio
async def test_authenticate_agent_invalid_key():
    """Test authentication with invalid API key."""
    with pytest.raises(ValueError, match="API key not found"):
        await authenticate_agent("invalid_key", db_session)


@pytest.mark.asyncio
async def test_hash_api_key():
    """Test API key hashing."""
    key = "my_secret_key_123"
    hash1 = await hash_api_key(key)
    hash2 = await hash_api_key(key)
    
    # Same key produces same hash
    assert hash1 == hash2
    # Hash is deterministic
    assert len(hash1) == 64  # SHA256 hex is 64 chars
```

### 2. Integration tests: `tests/test_mcp_auth.py`

```python
"""Tests for MCP tool authentication."""
import pytest
from mcp_server.tools import get_context_authenticated, log_decision_authenticated


@pytest.mark.asyncio
async def test_get_context_with_auth():
    """Test get_context tool with valid API key."""
    input = GetContextInput(project_id="proj-1")
    
    result = await get_context_authenticated(input, api_key="valid_key")
    
    assert result["stack"] is not None
    # Audit log should have entry with status=success


@pytest.mark.asyncio
async def test_get_context_auth_failure():
    """Test get_context tool with invalid API key."""
    input = GetContextInput(project_id="proj-1")
    
    with pytest.raises(ValueError, match="API key not found"):
        await get_context_authenticated(input, api_key="invalid_key")
    
    # Audit log should have entry with status=denied


@pytest.mark.asyncio
async def test_agent_project_mismatch():
    """Test that agent cannot access unauthorized project."""
    # Agent is assigned to proj-1, tries to access proj-2
    input = LogDecisionInput(
        project_id="proj-2",
        decision="test",
        reasoning="test",
    )
    
    with pytest.raises(PermissionError, match="not authorized"):
        await log_decision_authenticated(input, api_key="valid_key_for_proj1")
    
    # Audit log should have entry with status=denied
```

---

## Implementation Checklist

- [ ] Create Alembic migration for agent_id columns in decisions, sessions
- [ ] Create Django migration for agents, api_keys, audit_log tables
- [ ] Update core/models.py with agent_id columns
- [ ] Create core/auth.py with authenticate_agent(), hash_api_key()
- [ ] Create core/audit.py with log_audit_event()
- [ ] Update core/storage.py with read functions for auth (get_api_key_by_hash, get_agent_by_id, create_audit_log_entry)
- [ ] Update core/services.py: add (agent_id, user_id) params to all tool functions
- [ ] Create mcp_server/auth_middleware.py with @require_auth decorator
- [ ] Update mcp_server/tools.py: apply @require_auth to all tools, add agent_id/user_id to inputs
- [ ] Update mcp_server/server.py: register authenticated tool versions
- [ ] Write unit tests in tests/test_auth.py
- [ ] Write integration tests in tests/test_mcp_auth.py
- [ ] Update CLAUDE.md if needed
- [ ] Run all tests and verify coverage

---

## Key Constraints

1. **No breaking changes to existing context tables.** agent_id is NEW columns, not a refactor.
2. **Core has no framework imports.** auth.py and audit.py are plain Python. Django models imported only in storage.py.
3. **MCP server is thin.** All logic in core services. MCP only handles auth/audit/forwarding.
4. **Backward compatibility.** Local mode (Phase 1) still works with api_key=None and agent_id=None.
5. **Synchronous audit logging.** Audit entries are written before tool response, so nothing is lost.

---

## Deferred to Phase 2

- Key rotation/revocation
- Rate limiting
- Audit log retention policies
- Agent-side audit log export
- TLS enforcement (ops/deployment)

---

## Dependencies

- No new external libraries (uses only hashlib, uuid, sqlalchemy, django)
- Alembic for core migrations (already in use)
- Django for agent/api_keys/audit_log tables

---

## Success Criteria

- ✅ All 5 MCP tools require valid API key
- ✅ Agents can only access their assigned project
- ✅ All tool calls are logged to audit_log
- ✅ Secrets are redacted before storage
- ✅ Tests pass (unit + integration)
- ✅ No breaking changes to existing data
