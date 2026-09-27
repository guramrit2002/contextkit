"""Client authentication, project authorization, and audited tool execution."""
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
class ClientContext:
    """Identity of the authenticated client (API key holder) making the current call."""

    client_id: str
    user_id: str
    project_id: str


_current_client: ContextVar[Optional[ClientContext]] = ContextVar("current_client", default=None)


def current_client() -> Optional[ClientContext]:
    """The client authenticated for the call in progress, or None in local mode."""
    return _current_client.get()


def hash_api_key(api_key: str) -> str:
    # Must stay identical to api/clients/services.hash_api_key, which issues the keys.
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def authenticate_client(api_key: str) -> ClientContext:
    """Resolve an API key to its client. Raises AuthenticationError if it matches none."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise AuthenticationError("API key is required")
    if len(api_key) > MAX_API_KEY_LENGTH:
        raise AuthenticationError("Invalid API key")

    client = storage.get_client_by_key_hash(hash_api_key(api_key.strip()))
    if client is None:
        raise AuthenticationError("Invalid API key")

    return ClientContext(
        client_id=client["id"],
        user_id=client["user_id"],
        project_id=client["project_id"],
    )


def validate_client_project_access(
    client: ClientContext, requested_project_id: Optional[str]
) -> str:
    """Return the project the client may act on. An omitted project means its assigned one."""
    if requested_project_id and requested_project_id != client.project_id:
        raise AuthorizationError(
            f"Client is not authorized for project {requested_project_id}"
        )
    return client.project_id


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def authenticate_request(
    tool_name: str,
    api_key: Optional[str],
    requested_project_id: Optional[str],
    key_required: bool,
    started: Optional[float] = None,
) -> Optional[ClientContext]:
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
        return authenticate_client(api_key)
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
    Authenticate, authorize, run the operation as that client, and audit the outcome.

    Without an API key the call runs in local single-user mode (no client, no audit)
    unless REQUIRE_AUTH is set, in which case it is denied.
    """
    started = time.monotonic()
    client = authenticate_request(
        tool_name, api_key, requested_project_id, config.auth_required(), started
    )
    if client is None:
        return await operation()
    return await run_as_client(tool_name, client, requested_project_id, operation, started)


async def run_as_client(
    tool_name: str,
    client: ClientContext,
    requested_project_id: Optional[str],
    operation: Callable[[], Awaitable[T]],
    started: Optional[float] = None,
) -> T:
    """Check the client's project, run the operation as that client, and audit the outcome."""
    started = time.monotonic() if started is None else started

    def elapsed_ms() -> int:
        return _elapsed_ms(started)

    audit_ids = {"client_id": client.client_id, "user_id": client.user_id}
    try:
        project_id = validate_client_project_access(client, requested_project_id)
    except AuthorizationError as exc:
        log_audit_event(
            tool_name, "denied", project_id=requested_project_id,
            error_message=str(exc), duration_ms=elapsed_ms(), **audit_ids,
        )
        raise

    token = _current_client.set(client)
    try:
        result = await operation()
    except Exception as exc:
        log_audit_event(
            tool_name, "error", project_id=project_id,
            error_message=f"{type(exc).__name__}: {exc}", duration_ms=elapsed_ms(), **audit_ids,
        )
        raise
    finally:
        _current_client.reset(token)

    log_audit_event(
        tool_name, "success", project_id=project_id, duration_ms=elapsed_ms(), **audit_ids
    )
    return result
