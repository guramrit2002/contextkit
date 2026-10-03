"""Database storage layer for contextkit."""
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from core.config import (
    config,
    is_sqlite,
    resolve_database_url,
    resolve_db_path,
    resolve_django_database_url,
    resolve_django_db_path,
)
from core.errors import StorageError, ValidationError
from core.models import ApiKey, AuditLog, Client, Decision, Project, State
from core.projects import normalize_project_id

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASELINE_REVISION = "0001"
URL_PREFIXES = ("http://", "https://", "git@", "ssh://")

# One engine (and pool) per database URL per process. Keyed by URL so tests that switch
# databases through the environment still get the right one.
_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker] = {}


def get_db_path() -> str:
    """Get the path to the local SQLite contextkit database."""
    return str(resolve_db_path())


def _new_engine(url: str) -> Engine:
    if is_sqlite(url):
        return create_engine(url, echo=False, poolclass=NullPool)
    # Small pool: the Supabase session pooler caps connections per project.
    return create_engine(url, echo=False, pool_size=5, max_overflow=5, pool_pre_ping=True)


def get_engine() -> Engine:
    """The shared engine for core's database. Never dispose it; it is reused."""
    url = resolve_database_url()
    engine = _engines.get(url)
    if engine is None:
        engine = _engines[url] = _new_engine(url)
    return engine


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Alembic's config uses ConfigParser interpolation: escape URL-encoded "%" in passwords.
    cfg.set_main_option("sqlalchemy.url", resolve_database_url().replace("%", "%%"))
    return cfg


def init_db():
    """Create or upgrade core tables to the latest migration."""
    tables = set(inspect(get_engine()).get_table_names())

    cfg = _alembic_config()
    # Databases created by create_all() before Alembic have the baseline schema but no version.
    if "projects" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")


def get_session() -> Session:
    """Get a database session on the shared engine."""
    url = resolve_database_url()
    maker = _sessionmakers.get(url)
    if maker is None:
        maker = _sessionmakers[url] = sessionmaker(bind=get_engine())
    return maker()


def detect_project_id() -> str:
    """Detect project ID from git remote or current directory (local mode only)."""
    if config.is_hosted():
        # The server's own clone and working directory say nothing about the caller's project.
        raise ValidationError("project_id is required")
    try:
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"], text=True, cwd=os.getcwd()
        ).strip()
        if remote_url:
            return normalize_project_id(remote_url)
    except Exception:
        pass

    return normalize_project_id(os.getcwd())


def get_or_create_project(project_id: str, session: Session) -> Project:
    """Get or create a project."""
    stmt = select(Project).where(Project.id == project_id)
    project = session.execute(stmt).scalar_one_or_none()

    if not project:
        if config.is_hosted():
            # Never record the server's own git remote or paths for a caller's project.
            git_remote = project_id if project_id.startswith(URL_PREFIXES) else None
            local_path = None
        else:
            try:
                git_remote = subprocess.check_output(
                    ["git", "config", "--get", "remote.origin.url"], text=True
                ).strip()
                git_remote = normalize_project_id(git_remote) if git_remote else None
            except Exception:
                git_remote = None
            local_path = os.getcwd()

        project = Project(
            id=project_id,
            name=os.path.basename(project_id),
            git_remote=git_remote,
            local_path=local_path,
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
                    "client_id": d.client_id,
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
                    "client_id": s.client_id,
                    "summary": s.summary,
                    "decisions_made": s.decisions_made,
                    "created_at": s.created_at.isoformat(),
                }
                for s in sessions[-10:]
            ],
        }
    finally:
        session.close()


def _owner(user_id: Optional[str]) -> dict[str, str]:
    # Omit when unknown so the column default (config user) applies instead of NULL.
    return {"user_id": user_id} if user_id else {}


async def create_decision(
    project_id: str,
    decision: str,
    reasoning: str,
    alternatives_considered: Optional[str] = None,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
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
            client_id=client_id,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives_considered,
            **_owner(user_id),
        )
        session.add(new_decision)
        session.commit()

        return {
            "id": decision_id,
            "project_id": project_id,
            "client_id": client_id,
            "user_id": new_decision.user_id,
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
    user_id: Optional[str] = None,
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
            if user_id:
                state.user_id = user_id
        else:
            state = State(
                id=str(uuid.uuid4()),
                project_id=project_id,
                progress=progress,
                next_steps=next_steps,
                blockers=blockers,
                **_owner(user_id),
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
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
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
            client_id=client_id,
            summary=summary,
            decisions_made=decisions_made,
            **_owner(user_id),
        )
        session_db.add(new_session)
        session_db.commit()

        return {
            "id": session_id,
            "project_id": project_id,
            "client_id": client_id,
            "user_id": new_session.user_id,
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


def get_django_engine() -> Engine:
    """
    Engine for Django's tables (clients, api_keys). Locally a separate, one-off read-only
    SQLite engine; on Postgres the shared core engine, since both live in one database.
    """
    if not is_sqlite(resolve_django_database_url()):
        return get_engine()
    path = resolve_django_db_path()
    # mode=ro: core never writes Django's tables, and a missing file is an error rather than
    # SQLite silently creating an empty database.
    return create_engine(
        f"sqlite:///file:{path}?mode=ro&uri=true", echo=False, poolclass=NullPool
    )


def _client_tables_missing(engine) -> bool:
    if is_sqlite(resolve_django_database_url()) and not resolve_django_db_path().exists():
        return True
    return not inspect(engine).has_table("api_keys")


def _django_database_label() -> str:
    # Never include DATABASE_URL itself: it carries the password.
    if is_sqlite(resolve_django_database_url()):
        return str(resolve_django_db_path())
    return "the DATABASE_URL database"


def get_client_by_key_hash(key_hash: str) -> Optional[dict[str, Any]]:
    """Look up the client that owns an API key hash (api_keys joined to clients)."""
    sqlite = is_sqlite(resolve_django_database_url())
    engine = get_django_engine()
    session = Session(bind=engine)
    try:
        if not sqlite:
            # Postgres counterpart of SQLite's mode=ro: this transaction cannot write, so core
            # never writes Django's tables. Per transaction, so it works through the pooler.
            session.execute(text("SET TRANSACTION READ ONLY"))
        stmt = (
            select(Client)
            .join(ApiKey, ApiKey.client_id == Client.id)
            .where(ApiKey.key_hash == key_hash)
        )
        client = session.execute(stmt).scalar_one_or_none()
    except DBAPIError as exc:
        session.rollback()
        if _client_tables_missing(engine):
            raise StorageError(
                f"Client tables not found in {_django_database_label()}. Run "
                "`python manage.py migrate` in api/ with the same DATABASE_URL "
                "(or DJANGO_DB_PATH for local SQLite) first."
            ) from exc
        raise
    finally:
        session.close()
        if sqlite:
            engine.dispose()

    if client is None:
        return None
    return {
        "id": client.id,
        "user_id": client.user_id,
        "project_id": client.project_id,
        "name": client.name,
    }


def create_audit_log_entry(
    tool_name: str,
    status: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> str:
    """Append one audit_log row and return its id."""
    session = get_session()
    try:
        entry = AuditLog(
            id=str(uuid.uuid4()),
            client_id=client_id,
            tool_name=tool_name,
            project_id=project_id,
            user_id=user_id,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        session.add(entry)
        session.commit()
        return entry.id
    finally:
        session.close()
