"""Input validation for MCP tools."""
from typing import Optional

from core.redaction import validate_project_id, validate_text


def validate_get_context_input(project_id: Optional[str]) -> str:
    """Validate get_context tool input."""
    if project_id:
        return validate_project_id(project_id)
    return ""  # Will be auto-detected in services


def validate_log_decision_input(
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
) -> tuple[str, str, Optional[str]]:
    """Validate log_decision tool input."""
    decision = validate_text(decision, "decision", max_length=5000)
    reasoning = validate_text(reasoning, "reasoning", max_length=10000)
    if alternatives_considered:
        alternatives_considered = validate_text(
            alternatives_considered, "alternatives_considered", max_length=5000
        )
    return decision, reasoning, alternatives_considered


def validate_update_state_input(
    progress: str,
    next_steps: str,
    blockers: Optional[str] = None,
) -> tuple[str, str, Optional[str]]:
    """Validate update_state tool input."""
    progress = validate_text(progress, "progress", max_length=10000)
    next_steps = validate_text(next_steps, "next_steps", max_length=10000)
    if blockers:
        blockers = validate_text(blockers, "blockers", max_length=5000)
    return progress, next_steps, blockers


def validate_log_session_input(
    summary: str,
    decisions_made: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Validate log_session tool input."""
    summary = validate_text(summary, "summary", max_length=10000)
    if decisions_made:
        decisions_made = validate_text(decisions_made, "decisions_made", max_length=5000)
    return summary, decisions_made


def validate_export_markdown_input(
    project_id: Optional[str],
    output_path: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Validate export_markdown tool input."""
    if project_id:
        project_id = validate_project_id(project_id)
    if output_path:
        if not isinstance(output_path, str):
            raise TypeError("output_path must be a string")
        if len(output_path) > 500:
            raise ValueError("output_path is too long")
    return project_id, output_path
