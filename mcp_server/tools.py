"""MCP tool definitions for contextkit."""
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GetContextInput(BaseModel):
    """Input for get_context tool."""

    project_id: str | None = Field(
        None,
        description="Project ID. If not provided, inferred from git remote or current path.",
    )


class LogDecisionInput(BaseModel):
    """Input for log_decision tool."""

    decision: str = Field(description="What decision was made")
    reasoning: str = Field(description="Why this decision was made")
    alternatives_considered: str | None = Field(
        None, description="Other options that were considered"
    )
    project_id: str | None = Field(None, description="Project ID (auto-detected if omitted)")


class UpdateStateInput(BaseModel):
    """Input for update_state tool."""

    progress: str = Field(description="What has been completed so far")
    next_steps: str = Field(description="What comes next")
    blockers: str | None = Field(None, description="Current blockers or challenges")
    project_id: str | None = Field(None, description="Project ID (auto-detected if omitted)")


class LogSessionInput(BaseModel):
    """Input for log_session tool."""

    summary: str = Field(description="Summary of work completed in this session")
    decisions_made: str | None = Field(None, description="Key decisions made during the session")
    project_id: str | None = Field(None, description="Project ID (auto-detected if omitted)")


class ExportMarkdownInput(BaseModel):
    """Input for export_markdown tool."""

    project_id: str | None = Field(None, description="Project ID (auto-detected if omitted)")
    output_path: str | None = Field(None, description="Path to save the markdown file")


async def get_context(input: GetContextInput) -> dict[str, Any]:
    """
    Return the project briefing for the agent to load.

    Returns: briefing dict with stack, decisions, current state, and recent sessions.
    """
    from core import services

    project_id = input.project_id
    briefing = await services.get_briefing(project_id)
    return briefing


async def get_context_flat(
    project_id: str | None = None,
) -> dict[str, Any]:
    """
    Return the project briefing for the agent to load.

    Returns: briefing dict with stack, decisions, current state, and recent sessions.
    """
    from core import services

    return await services.get_briefing(project_id)


async def log_decision(input: LogDecisionInput) -> dict[str, Any]:
    """Record a decision and its reasoning."""
    from core import services

    decision_record = await services.log_decision(
        project_id=input.project_id,
        decision=input.decision,
        reasoning=input.reasoning,
        alternatives_considered=input.alternatives_considered,
    )
    return {"success": True, "decision_id": decision_record.get("id")}


async def update_state(input: UpdateStateInput) -> dict[str, Any]:
    """Replace the current state: progress, next steps, blockers."""
    from core import services

    await services.update_state(
        project_id=input.project_id,
        progress=input.progress,
        next_steps=input.next_steps,
        blockers=input.blockers,
    )
    return {"success": True}


async def log_session(input: LogSessionInput) -> dict[str, Any]:
    """Append a summary of the work session."""
    from core import services

    session_record = await services.log_session(
        project_id=input.project_id,
        summary=input.summary,
        decisions_made=input.decisions_made,
    )
    return {"success": True, "session_id": session_record.get("id")}


async def export_markdown(input: ExportMarkdownInput) -> dict[str, Any]:
    """Export the project context as a readable markdown file."""
    from core import services

    markdown_content = await services.export_markdown(input.project_id)
    if input.output_path:
        output_path = Path(input.output_path).expanduser()
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_content, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write markdown export to {output_path}: {exc}") from exc
    return {"success": True, "markdown": markdown_content}


async def export_markdown_flat(
    input: ExportMarkdownInput | None = None,
    project_id: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Export the project context as a readable markdown file."""
    from core import services

    if input is not None:
        project_id = input.project_id
        output_path = input.output_path

    markdown_content = await services.export_markdown(project_id)
    if output_path:
        output = Path(output_path).expanduser()
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown_content, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write markdown export to {output}: {exc}") from exc
    return {"success": True, "markdown": markdown_content}
