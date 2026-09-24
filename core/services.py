"""Core business logic and services for contextkit."""
import logging
from typing import Any, Optional

from core.redaction import SecretRedactor
from core.validation import (
    validate_export_markdown_input,
    validate_get_context_input,
    validate_log_decision_input,
    validate_log_session_input,
    validate_update_state_input,
)

logger = logging.getLogger(__name__)


async def get_briefing(project_id: Optional[str] = None) -> dict[str, Any]:
    """
    Get the project briefing for an agent to load.

    Returns the stack, key decisions, current state, and recent sessions.
    """
    from core import storage

    try:
        project_id = validate_get_context_input(project_id) or storage.detect_project_id()
        briefing = await storage.get_briefing(project_id)
        return briefing
    except Exception as e:
        logger.error(f"Failed to get briefing: {e}")
        raise


async def log_decision(
    project_id: Optional[str],
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
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

        project_id = project_id or storage.detect_project_id()
        decision_record = await storage.create_decision(
            project_id=project_id,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives_considered,
        )
        return decision_record
    except Exception as e:
        logger.error(f"Failed to log decision: {e}")
        raise


async def update_state(
    project_id: Optional[str],
    progress: str,
    next_steps: str,
    blockers: Optional[str] = None,
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

        project_id = project_id or storage.detect_project_id()
        state_record = await storage.update_state(
            project_id=project_id,
            progress=progress,
            next_steps=next_steps,
            blockers=blockers,
        )
        return state_record
    except Exception as e:
        logger.error(f"Failed to update state: {e}")
        raise


async def log_session(
    project_id: Optional[str],
    summary: str,
    decisions_made: Optional[str] = None,
) -> dict[str, Any]:
    """Log a work session."""
    from core import storage

    try:
        summary, decisions_made = validate_log_session_input(summary, decisions_made)

        # Redact secrets before storing
        summary = SecretRedactor.redact(summary)
        if decisions_made:
            decisions_made = SecretRedactor.redact(decisions_made)

        project_id = project_id or storage.detect_project_id()
        session_record = await storage.create_session(
            project_id=project_id,
            summary=summary,
            decisions_made=decisions_made,
        )
        return session_record
    except Exception as e:
        logger.error(f"Failed to log session: {e}")
        raise


async def export_markdown(project_id: Optional[str] = None) -> str:
    """Export the project context as markdown."""
    from core import storage

    try:
        project_id, _ = validate_export_markdown_input(project_id)
        project_id = project_id or storage.detect_project_id()
        markdown = await storage.export_markdown(project_id)
        return markdown
    except Exception as e:
        logger.error(f"Failed to export markdown: {e}")
        raise
