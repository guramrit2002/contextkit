"""Core business logic and services for contextkit."""
import logging
from typing import Any, NamedTuple, Optional

from core.auth import current_client, validate_client_project_access
from core.redaction import SecretRedactor, validate_project_id
from core.validation import (
    validate_export_markdown_input,
    validate_get_context_input,
    validate_log_decision_input,
    validate_log_session_input,
    validate_update_state_input,
)

logger = logging.getLogger(__name__)


class Identity(NamedTuple):
    project_id: str
    client_id: Optional[str]
    user_id: Optional[str]


def _resolve_identity(
    project_id: Optional[str], client_id: Optional[str], user_id: Optional[str]
) -> Identity:
    """Fill client/user/project from the authenticated client, if any, and enforce its project."""
    from core import storage

    if project_id:
        # Every tool's project ID is validated and normalized here, so all callers agree.
        project_id = validate_project_id(project_id)
    client = current_client()
    if client is not None:
        project_id = validate_client_project_access(client, project_id)
        client_id = client_id or client.client_id
        user_id = user_id or client.user_id
    return Identity(project_id or storage.detect_project_id(), client_id, user_id)


async def get_briefing(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get the project briefing for an agent to load.

    Returns the stack, key decisions, current state, and recent sessions.
    """
    from core import storage

    try:
        identity = _resolve_identity(
            validate_get_context_input(project_id) or None, client_id, user_id
        )
        return await storage.get_briefing(identity.project_id)
    except Exception as e:
        logger.error(f"Failed to get briefing: {e}")
        raise


async def log_decision(
    project_id: Optional[str],
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Record a decision and its reasoning."""
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

        identity = _resolve_identity(project_id, client_id, user_id)
        return await storage.create_decision(
            project_id=identity.project_id,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives_considered,
            client_id=identity.client_id,
            user_id=identity.user_id,
        )
    except Exception as e:
        logger.error(f"Failed to log decision: {e}")
        raise


async def update_state(
    project_id: Optional[str],
    progress: str,
    next_steps: str,
    blockers: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Update the current project state."""
    from core import storage

    try:
        progress, next_steps, blockers = validate_update_state_input(
            progress, next_steps, blockers
        )

        # Redact secrets before storing
        progress = SecretRedactor.redact(progress)
        next_steps = SecretRedactor.redact(next_steps)
        if blockers:
            blockers = SecretRedactor.redact(blockers)

        identity = _resolve_identity(project_id, client_id, user_id)
        return await storage.update_state(
            project_id=identity.project_id,
            progress=progress,
            next_steps=next_steps,
            blockers=blockers,
            user_id=identity.user_id,
        )
    except Exception as e:
        logger.error(f"Failed to update state: {e}")
        raise


async def log_session(
    project_id: Optional[str],
    summary: str,
    decisions_made: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Log a work session."""
    from core import storage

    try:
        summary, decisions_made = validate_log_session_input(summary, decisions_made)

        # Redact secrets before storing
        summary = SecretRedactor.redact(summary)
        if decisions_made:
            decisions_made = SecretRedactor.redact(decisions_made)

        identity = _resolve_identity(project_id, client_id, user_id)
        return await storage.create_session(
            project_id=identity.project_id,
            summary=summary,
            decisions_made=decisions_made,
            client_id=identity.client_id,
            user_id=identity.user_id,
        )
    except Exception as e:
        logger.error(f"Failed to log session: {e}")
        raise


async def export_markdown(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Export the project context as markdown."""
    from core import storage

    try:
        project_id, _ = validate_export_markdown_input(project_id)
        identity = _resolve_identity(project_id, client_id, user_id)
        return await storage.export_markdown(identity.project_id)
    except Exception as e:
        logger.error(f"Failed to export markdown: {e}")
        raise
