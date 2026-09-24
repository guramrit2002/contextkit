"""SQLAlchemy models for contextkit database."""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship

from core.config import config

Base = declarative_base()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def get_default_user_id() -> str:
    """Get default user ID from config."""
    return config.get_default_user_id()


class Project(Base):
    """Represents a project/codebase."""

    __tablename__ = "projects"

    id = Column(String(500), primary_key=True)
    name = Column(String(255), nullable=False)
    git_remote = Column(String(500))
    local_path = Column(String(500))
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    decisions = relationship("Decision", back_populates="project", cascade="all, delete-orphan")
    state = relationship("State", back_populates="project", uselist=False, cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")


class Decision(Base):
    """Represents a recorded decision."""

    __tablename__ = "decisions"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(500), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    decision = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False)
    alternatives_considered = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    project = relationship("Project", back_populates="decisions")


class State(Base):
    """Represents the current project state."""

    __tablename__ = "state"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(500), ForeignKey("projects.id"), nullable=False, unique=True)
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    progress = Column(Text, nullable=False)
    next_steps = Column(Text, nullable=False)
    blockers = Column(Text)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="state")


class Session(Base):
    """Represents a work session."""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(500), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(255), nullable=False, default=get_default_user_id)
    summary = Column(Text, nullable=False)
    decisions_made = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    project = relationship("Project", back_populates="sessions")
