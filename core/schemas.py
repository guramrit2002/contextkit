"""Pydantic schemas for contextkit data models."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectSchema(BaseModel):
    """Schema for a project."""

    id: str = Field(description="Project identifier")
    name: str = Field(description="Project name")
    git_remote: Optional[str] = Field(None, description="Git remote URL")
    local_path: str = Field(description="Local path to project")
    created_at: datetime
    updated_at: datetime


class DecisionSchema(BaseModel):
    """Schema for a recorded decision."""

    id: str
    project_id: str
    decision: str
    reasoning: str
    alternatives_considered: Optional[str] = None
    created_at: datetime


class StateSchema(BaseModel):
    """Schema for project current state."""

    id: str
    project_id: str
    progress: str
    next_steps: str
    blockers: Optional[str] = None
    updated_at: datetime


class SessionSchema(BaseModel):
    """Schema for a work session."""

    id: str
    project_id: str
    summary: str
    decisions_made: Optional[str] = None
    created_at: datetime


class BriefingSchema(BaseModel):
    """Schema for project briefing returned to agents."""

    project: ProjectSchema
    decisions: list[DecisionSchema]
    current_state: Optional[StateSchema] = None
    recent_sessions: list[SessionSchema]
