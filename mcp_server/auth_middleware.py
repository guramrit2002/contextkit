"""Attach agent authentication to MCP tools. All auth logic lives in core.auth."""
import functools
import os
from typing import Any, Awaitable, Callable, Optional

from fastmcp.server.dependencies import get_http_request

from core.auth import guarded_call

API_KEY_ENV = "CONTEXTKIT_API_KEY"


def _http_headers() -> Optional[dict[str, str]]:
    """Lower-cased request headers over HTTP, or None over stdio."""
    try:
        request = get_http_request()
    except RuntimeError:
        return None
    return {name.lower(): value for name, value in request.headers.items()}


def resolve_api_key() -> Optional[str]:
    """
    Over HTTP the key comes only from `Authorization: Bearer <key>`. The server's own
    CONTEXTKIT_API_KEY must never apply to HTTP callers, or every keyless request would
    run as that agent. Over stdio the key comes from CONTEXTKIT_API_KEY in the MCP config.
    """
    headers = _http_headers()
    if headers is None:
        return os.getenv(API_KEY_ENV) or None

    authorization = headers.get("authorization", "").strip()
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    # A malformed header is still an attempt to authenticate: pass it on so it is denied.
    return authorization


def _requested_project_id(args: tuple, kwargs: dict) -> Optional[str]:
    if kwargs.get("project_id"):
        return kwargs["project_id"]
    for value in (kwargs.get("input"), *args):
        project_id = getattr(value, "project_id", None)
        if project_id:
            return project_id
    return None


def require_auth(tool_name: str):
    """Run the tool through core.auth.guarded_call with the caller's API key."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await guarded_call(
                tool_name,
                resolve_api_key(),
                _requested_project_id(args, kwargs),
                lambda: func(*args, **kwargs),
            )

        return wrapper

    return decorator
