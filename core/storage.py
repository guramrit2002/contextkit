"""Database storage layer for contextkit."""
import os
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from core.models import Base, Decision, Project, State


def get_db_path() -> str:
    """Get the path to the contextkit database."""
    configured_path = os.environ.get("CONTEXTKIT_DB_PATH")
    if configured_path:
        return os.path.abspath(os.path.expanduser(configured_path))

    # Use db.sqlite3 in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "db.sqlite3")


def get_engine():
    """Get SQLAlchemy engine."""
    db_path = get_db_path()
    return create_engine(f"sqlite:///{db_path}", echo=False, poolclass=NullPool)


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def get_session() -> Session:
    """Get a database session."""
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def detect_project_id() -> str:
    """Detect project ID from git remote or current directory."""
    try:
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"], text=True, cwd=os.getcwd()
        ).strip()
        if remote_url:
            return remote_url
    except Exception:
        pass

    return os.getcwd()


def get_or_create_project(project_id: str, session: Session) -> Project:
    """Get or create a project."""
    stmt = select(Project).where(Project.id == project_id)
    project = session.execute(stmt).scalar_one_or_none()

    if not project:
        # Create new project
        try:
            git_remote = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"], text=True
            ).strip()
        except Exception:
            git_remote = None

        project = Project(
            id=project_id,
            name=os.path.basename(project_id),
            git_remote=git_remote,
            local_path=os.getcwd(),
        )
        session.add(project)
        session.commit()

    return project


async def get_briefing(project_id: str) -> dict[str, Any]:
    """Retrieve project briefing from database."""
    session = get_session()
    try:
        # Get or create project
        project = get_or_create_project(project_id, session)

        # Get all decisions
        decisions_stmt = (
            select(Decision)
            .where(Decision.project_id == project_id)
            .order_by(Decision.created_at.asc())
        )
        decisions = session.execute(decisions_stmt).scalars().all()

        # Get current state
        state_stmt = select(State).where(State.project_id == project_id)
        state = session.execute(state_stmt).scalar_one_or_none()

        from core.models import Session as SessionModel

        sessions_stmt = (
            select(SessionModel)
            .where(SessionModel.project_id == project_id)
            .order_by(SessionModel.created_at.asc())
        )
        sessions = session.execute(sessions_stmt).scalars().all()

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "git_remote": project.git_remote,
                "local_path": project.local_path,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
            },
            "decisions": [
                {
                    "id": d.id,
                    "decision": d.decision,
                    "reasoning": d.reasoning,
                    "alternatives_considered": d.alternatives_considered,
                    "created_at": d.created_at.isoformat(),
                }
                for d in decisions
            ],
            "current_state": {
                "id": state.id,
                "progress": state.progress,
                "next_steps": state.next_steps,
                "blockers": state.blockers,
                "updated_at": state.updated_at.isoformat(),
            } if state else None,
            "recent_sessions": [
                {
                    "id": s.id,
                    "project_id": s.project_id,
                    "summary": s.summary,
                    "decisions_made": s.decisions_made,
                    "created_at": s.created_at.isoformat(),
                }
                for s in sessions[-10:]
            ],
        }
    finally:
        session.close()


async def create_decision(
    project_id: str,
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
) -> dict[str, Any]:
    """Store a decision in the database."""
    session = get_session()
    try:
        # Ensure project exists
        get_or_create_project(project_id, session)

        decision_id = str(uuid.uuid4())
        new_decision = Decision(
            id=decision_id,
            project_id=project_id,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives_considered,
        )
        session.add(new_decision)
        session.commit()

        return {
            "id": decision_id,
            "project_id": project_id,
            "decision": decision,
            "reasoning": reasoning,
            "alternatives_considered": alternatives_considered,
            "created_at": new_decision.created_at.isoformat(),
        }
    finally:
        session.close()


async def update_state(
    project_id: str,
    progress: str,
    next_steps: str,
    blockers: Optional[str] = None,
) -> dict[str, Any]:
    """Update the current state in the database."""
    session = get_session()
    try:
        # Ensure project exists
        get_or_create_project(project_id, session)

        # Get existing state or create new
        state_stmt = select(State).where(State.project_id == project_id)
        state = session.execute(state_stmt).scalar_one_or_none()

        if state:
            state.progress = progress
            state.next_steps = next_steps
            state.blockers = blockers
            state.updated_at = datetime.now(UTC)
        else:
            state = State(
                id=str(uuid.uuid4()),
                project_id=project_id,
                progress=progress,
                next_steps=next_steps,
                blockers=blockers,
            )
            session.add(state)

        session.commit()

        return {
            "id": state.id,
            "project_id": project_id,
            "progress": progress,
            "next_steps": next_steps,
            "blockers": blockers,
            "updated_at": state.updated_at.isoformat(),
        }
    finally:
        session.close()


async def create_session(
    project_id: str,
    summary: str,
    decisions_made: Optional[str] = None,
) -> dict[str, Any]:
    """Store a session summary in the database."""
    from core.models import Session as SessionModel

    session_db = get_session()
    try:
        # Ensure project exists
        get_or_create_project(project_id, session_db)

        session_id = str(uuid.uuid4())
        new_session = SessionModel(
            id=session_id,
            project_id=project_id,
            summary=summary,
            decisions_made=decisions_made,
        )
        session_db.add(new_session)
        session_db.commit()

        return {
            "id": session_id,
            "project_id": project_id,
            "summary": summary,
            "decisions_made": decisions_made,
            "created_at": new_session.created_at.isoformat(),
        }
    finally:
        session_db.close()


async def export_markdown(project_id: str) -> str:
    """Export project context as markdown."""
    session = get_session()
    try:
        briefing = await get_briefing(project_id)

        project = briefing["project"]
        decisions = briefing["decisions"]
        state = briefing["current_state"]

        # Get recent sessions
        from core.models import Session as SessionModel

        sessions_stmt = select(SessionModel).where(SessionModel.project_id == project_id)
        sessions = session.execute(sessions_stmt).scalars().all()

        markdown = f"# Project Context: {project['name']}\n\n"
        markdown += f"**Project ID:** `{project['id']}`\n\n"

        if project["git_remote"]:
            markdown += f"**Git Remote:** {project['git_remote']}\n\n"

        markdown += "## Current State\n\n"
        if state:
            markdown += f"**Progress:**\n{state['progress']}\n\n"
            markdown += f"**Next Steps:**\n{state['next_steps']}\n\n"
            if state.get("blockers"):
                markdown += f"**Blockers:**\n{state['blockers']}\n\n"
        else:
            markdown += "(No state recorded yet)\n\n"

        markdown += "## Decisions\n\n"
        if decisions:
            for i, decision in enumerate(decisions, 1):
                markdown += f"### Decision {i}\n"
                markdown += f"**What:** {decision['decision']}\n\n"
                markdown += f"**Why:** {decision['reasoning']}\n\n"
                if decision.get("alternatives_considered"):
                    markdown += f"**Alternatives:** {decision['alternatives_considered']}\n\n"
                markdown += f"*Recorded: {decision['created_at']}*\n\n"
        else:
            markdown += "(No decisions recorded yet)\n\n"

        markdown += "## Recent Sessions\n\n"
        if sessions:
            for i, s in enumerate(sessions[-10:], 1):  # Last 10 sessions
                markdown += f"### Session {i}\n"
                markdown += f"{s.summary}\n\n"
                if s.decisions_made:
                    markdown += f"**Decisions Made:** {s.decisions_made}\n\n"
                markdown += f"*Date: {s.created_at.isoformat()}*\n\n"
        else:
            markdown += "(No sessions recorded yet)\n\n"

        return markdown
    finally:
        session.close()
