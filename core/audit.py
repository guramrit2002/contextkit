"""Audit logging for tool calls."""
import logging
from typing import Optional

from core import storage
from core.redaction import SecretRedactor

logger = logging.getLogger(__name__)

STATUSES = ("success", "error", "denied")
MAX_ERROR_LENGTH = 2000


def log_audit_event(
    tool_name: str,
    status: str,
    agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Record one tool call. A failure to write is logged and never fails the tool call."""
    if status not in STATUSES:
        raise ValueError(f"Unknown audit status: {status}")

    if error_message:
        # Exceptions can echo user input, and nothing is stored before redaction.
        error_message = SecretRedactor.redact(error_message)[:MAX_ERROR_LENGTH]

    try:
        storage.create_audit_log_entry(
            tool_name=tool_name,
            status=status,
            agent_id=agent_id,
            project_id=project_id,
            user_id=user_id,
            error_message=error_message,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.exception("Failed to write audit event for %s (%s)", tool_name, status)
