"""Agent authentication, project authorization, and audited tool execution."""
import hashlib
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

from core import storage
from core.audit import log_audit_event
from core.config import config
from core.errors import AuthenticationError, AuthorizationError

T = TypeVar("T")

MAX_API_KEY_LENGTH = 512


@dataclass(frozen=True)
class AgentContext:
    """Identity of the authenticated agent making the current call."""

    agent_id: str
    user_id: str
    project_id: str


_current_agent: ContextVar[Optional[AgentContext]] = ContextVar("current_agent", default=None)


def current_agent() -> Optional[AgentContext]:
    """The agent authenticated for the call in progress, or None in local mode."""
    return _current_agent.get()


def hash_api_key(api_key: str) -> str:
    # Must stay identical to api/agents/services.hash_api_key, which issues the keys.
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def authenticate_agent(api_key: str) -> AgentContext:
    """Resolve an API key to its agent. Raises AuthenticationError if it matches none."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise AuthenticationError("API key is required")
    if len(api_key) > MAX_API_KEY_LENGTH:
        raise AuthenticationError("Invalid API key")

    agent = storage.get_agent_by_key_hash(hash_api_key(api_key.strip()))
    if agent is None:
        raise AuthenticationError("Invalid API key")

    return AgentContext(
        agent_id=agent["id"],
        user_id=agent["user_id"],
        project_id=agent["project_id"],
    )


def validate_agent_project_access(
    agent: AgentContext, requested_project_id: Optional[str]
) -> str:
    """Return the project the agent may act on. An omitted project means its assigned one."""
    if requested_project_id and requested_project_id != agent.project_id:
        raise AuthorizationError(
            f"Agent is not authorized for project {requested_project_id}"
        )
    return agent.project_id


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def authenticate_request(
    tool_name: str,
    api_key: Optional[str],
    requested_project_id: Optional[str],
    key_required: bool,
    started: Optional[float] = None,
) -> Optional[AgentContext]:
    """
    Authenticate a transport request, auditing any denial.

    Returns None only for a keyless call when a key is not required (local mode).
    """
    started = time.monotonic() if started is None else started

    if not api_key:
        if not key_required:
            return None
        log_audit_event(
            tool_name, "denied", project_id=requested_project_id,
            error_message="API key is required", duration_ms=_elapsed_ms(started),
        )
        raise AuthenticationError("API key is required")

    try:
        return authenticate_agent(api_key)
    except AuthenticationError as exc:
        log_audit_event(
            tool_name, "denied", project_id=requested_project_id,
            error_message=str(exc), duration_ms=_elapsed_ms(started),
        )
        raise


async def guarded_call(
    tool_name: str,
    api_key: Optional[str],
    requested_project_id: Optional[str],
    operation: Callable[[], Awaitable[T]],
) -> T:
    """
    Authenticate, authorize, run the operation as that agent, and audit the outcome.

    Without an API key the call runs in local single-user mode (no agent, no audit)
    unless REQUIRE_AUTH is set, in which case it is denied.
    """
    started = time.monotonic()
    agent = authenticate_request(
        tool_name, api_key, requested_project_id, config.auth_required(), started
    )
    if agent is None:
        return await operation()
    return await run_as_agent(tool_name, agent, requested_project_id, operation, started)


async def run_as_agent(
    tool_name: str,
    agent: AgentContext,
    requested_project_id: Optional[str],
    operation: Callable[[], Awaitable[T]],
    started: Optional[float] = None,
) -> T:
    """Check the agent's project, run the operation as that agent, and audit the outcome."""
    started = time.monotonic() if started is None else started

    def elapsed_ms() -> int:
        return _elapsed_ms(started)

    audit_ids = {"agent_id": agent.agent_id, "user_id": agent.user_id}
    try:
        project_id = validate_agent_project_access(agent, requested_project_id)
    except AuthorizationError as exc:
        log_audit_event(
            tool_name, "denied", project_id=requested_project_id,
            error_message=str(exc), duration_ms=elapsed_ms(), **audit_ids,
        )
        raise

    token = _current_agent.set(agent)
    try:
        result = await operation()
    except Exception as exc:
        log_audit_event(
            tool_name, "error", project_id=project_id,
            error_message=f"{type(exc).__name__}: {exc}", duration_ms=elapsed_ms(), **audit_ids,
        )
        raise
    finally:
        _current_agent.reset(token)

    log_audit_event(
        tool_name, "success", project_id=project_id, duration_ms=elapsed_ms(), **audit_ids
    )
    return result
