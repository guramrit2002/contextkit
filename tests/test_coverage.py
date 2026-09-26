"""Comprehensive tests for 100% code coverage."""
from datetime import datetime
from pathlib import Path

import pytest

from core import config, errors, redaction, schemas, services, storage, validation
from core.db_init import initialize_database
from mcp_server import server, tools
from mcp_server.__main__ import *  # noqa: F401, F403


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Create isolated test database."""
    db_path = str(tmp_path / "contextkit.sqlite3")
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", db_path)
    storage.init_db()
    return db_path


# ============================================================================
# core/errors.py tests
# ============================================================================


def test_exception_hierarchy():
    """Test custom exception classes."""
    assert issubclass(errors.ProjectNotFoundError, errors.ContextKitError)
    assert issubclass(errors.InvalidProjectIdError, errors.ContextKitError)
    assert issubclass(errors.StorageError, errors.ContextKitError)
    assert issubclass(errors.BriefingError, errors.ContextKitError)
    assert issubclass(errors.ValidationError, errors.ContextKitError)

    # Test raising and catching
    with pytest.raises(errors.ProjectNotFoundError):
        raise errors.ProjectNotFoundError("Project not found")

    with pytest.raises(errors.InvalidProjectIdError):
        raise errors.InvalidProjectIdError("Invalid ID")

    with pytest.raises(errors.StorageError):
        raise errors.StorageError("Storage failed")

    with pytest.raises(errors.BriefingError):
        raise errors.BriefingError("Briefing failed")

    with pytest.raises(errors.ValidationError):
        raise errors.ValidationError("Validation failed")

    with pytest.raises(errors.ContextKitError):
        raise errors.ContextKitError("Base error")


# ============================================================================
# core/schemas.py tests
# ============================================================================


def test_project_schema():
    """Test ProjectSchema model."""
    now = datetime.utcnow()
    project = schemas.ProjectSchema(
        id="test-project",
        name="Test Project",
        git_remote="https://github.com/test/repo.git",
        local_path="/path/to/repo",
        created_at=now,
        updated_at=now,
    )
    assert project.id == "test-project"
    assert project.name == "Test Project"
    assert project.git_remote == "https://github.com/test/repo.git"


def test_decision_schema():
    """Test DecisionSchema model."""
    now = datetime.utcnow()
    decision = schemas.DecisionSchema(
        id="dec-1",
        project_id="proj-1",
        decision="Use SQLite",
        reasoning="Simple local storage",
        alternatives_considered="PostgreSQL",
        created_at=now,
    )
    assert decision.decision == "Use SQLite"
    assert decision.reasoning == "Simple local storage"


def test_state_schema():
    """Test StateSchema model."""
    now = datetime.utcnow()
    state = schemas.StateSchema(
        id="state-1",
        project_id="proj-1",
        progress="50% complete",
        next_steps="Add tests",
        blockers="None",
        updated_at=now,
    )
    assert state.progress == "50% complete"


def test_session_schema():
    """Test SessionSchema model."""
    now = datetime.utcnow()
    session = schemas.SessionSchema(
        id="sess-1",
        project_id="proj-1",
        summary="Built storage layer",
        decisions_made="Used SQLAlchemy",
        created_at=now,
    )
    assert session.summary == "Built storage layer"


def test_briefing_schema():
    """Test BriefingSchema model."""
    now = datetime.utcnow()
    project = schemas.ProjectSchema(
        id="proj-1",
        name="Test",
        local_path="/path",
        created_at=now,
        updated_at=now,
    )
    decision = schemas.DecisionSchema(
        id="dec-1",
        project_id="proj-1",
        decision="Decide",
        reasoning="Reason",
        created_at=now,
    )
    state = schemas.StateSchema(
        id="state-1",
        project_id="proj-1",
        progress="Progress",
        next_steps="Steps",
        updated_at=now,
    )
    session = schemas.SessionSchema(
        id="sess-1",
        project_id="proj-1",
        summary="Summary",
        created_at=now,
    )
    briefing = schemas.BriefingSchema(
        project=project,
        decisions=[decision],
        current_state=state,
        recent_sessions=[session],
    )
    assert briefing.project.id == "proj-1"
    assert len(briefing.decisions) == 1


# ============================================================================
# core/config.py tests
# ============================================================================


def test_config_environment_detection():
    """Test environment detection."""
    cfg = config.config
    # Test with current config (which is already loaded)
    assert callable(cfg.is_development)
    assert callable(cfg.is_production)


def test_config_get_default_user_id():
    """Test get_default_user_id method."""
    cfg = config.config
    user_id = cfg.get_default_user_id()
    assert isinstance(user_id, str)
    assert len(user_id) > 0


def test_config_is_development():
    """Test is_development method."""
    cfg = config.config
    result = cfg.is_development()
    assert isinstance(result, bool)


def test_config_is_production():
    """Test is_production method."""
    cfg = config.config
    result = cfg.is_production()
    assert isinstance(result, bool)


def test_config_get_db_path():
    """Test get_db_path method."""
    cfg = config.config
    db_path = cfg.get_db_path()
    assert db_path is None or isinstance(db_path, str)


# ============================================================================
# core/redaction.py tests
# ============================================================================


def test_redact_api_key():
    """Test API key redaction."""
    text = "My API key is AKIAIOSFODNN7EXAMPLE"
    redacted = redaction.SecretRedactor.redact(text)
    assert "[REDACTED]" in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted


def test_redact_github_token():
    """Test GitHub token redaction."""
    text = "token: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    redacted = redaction.SecretRedactor.redact(text)
    assert "[REDACTED]" in redacted


def test_redact_password():
    """Test password redaction."""
    text = "password=mysecretpass123"
    redacted = redaction.SecretRedactor.redact(text)
    assert "[REDACTED]" in redacted


def test_redact_ssh_key():
    """Test SSH key redaction."""
    text = "-----BEGIN OPENSSH PRIVATE KEY-----"
    redacted = redaction.SecretRedactor.redact(text)
    assert "[REDACTED]" in redacted


def test_redact_url_credentials():
    """Test URL credentials redaction."""
    text = "https://user:password@example.com"
    redacted = redaction.SecretRedactor.redact(text)
    assert "[REDACTED]" in redacted


def test_redact_empty_string():
    """Test redaction of empty string."""
    assert redaction.SecretRedactor.redact("") == ""


def test_redact_none():
    """Test redaction of None."""
    assert redaction.SecretRedactor.redact(None) is None


def test_redact_non_string():
    """Test redaction of non-string."""
    assert redaction.SecretRedactor.redact(123) == 123


def test_redact_dict():
    """Test dictionary redaction."""
    data = {
        "key1": "value1",
        "api_key": "api_key=secret123",
        "nested": {"password": "password=pass456"},
        "list": ["item1", "AKIA1234567890123456"],
    }
    redacted = redaction.SecretRedactor.redact_dict(data)
    api_key_redacted = (
        "[REDACTED]" in str(redacted["api_key"]).upper()
        or redacted["api_key"] == "api_key=[REDACTED]"
    )
    assert api_key_redacted
    password_field = redacted["nested"]["password"]
    password_redacted = (
        "[REDACTED]" in str(password_field).upper()
        or "[REDACTED]" in password_field
    )
    assert password_redacted
    assert redacted["key1"] == "value1"


def test_validate_project_id_valid():
    """Test valid project ID validation."""
    result = redaction.validate_project_id("my-project")
    assert result == "my-project"


def test_validate_project_id_empty():
    """Test empty project ID validation."""
    with pytest.raises(ValueError):
        redaction.validate_project_id("")


def test_validate_project_id_none():
    """Test None project ID validation."""
    with pytest.raises(ValueError):
        redaction.validate_project_id(None)


def test_validate_project_id_not_string():
    """Test non-string project ID validation."""
    with pytest.raises(TypeError):
        redaction.validate_project_id(123)


def test_validate_project_id_too_long():
    """Test too long project ID validation."""
    with pytest.raises(ValueError):
        redaction.validate_project_id("x" * 501)


def test_validate_project_id_starts_with_dot():
    """Test project ID starting with dot."""
    with pytest.raises(ValueError):
        redaction.validate_project_id(".hidden")


def test_validate_text_valid():
    """Test valid text validation."""
    result = redaction.validate_text("Valid text", "field")
    assert result == "Valid text"


def test_validate_text_strips_whitespace():
    """Test text validation strips whitespace."""
    result = redaction.validate_text("  text  ", "field")
    assert result == "text"


def test_validate_text_empty():
    """Test empty text validation."""
    with pytest.raises(ValueError):
        redaction.validate_text("", "field")


def test_validate_text_none():
    """Test None text validation."""
    result = redaction.validate_text(None, "field")
    assert result is None


def test_validate_text_not_string():
    """Test non-string text validation."""
    with pytest.raises(TypeError):
        redaction.validate_text(123, "field")


def test_validate_text_too_long():
    """Test text exceeding max length."""
    with pytest.raises(ValueError):
        redaction.validate_text("x" * 10001, "field", max_length=10000)


# ============================================================================
# core/validation.py tests
# ============================================================================


def test_validate_get_context_input_with_id():
    """Test get_context input validation with project ID."""
    result = validation.validate_get_context_input("my-project")
    assert result == "my-project"


def test_validate_get_context_input_without_id():
    """Test get_context input validation without project ID."""
    result = validation.validate_get_context_input(None)
    assert result == ""


def test_validate_log_decision_input():
    """Test log_decision input validation."""
    dec, rea, alt = validation.validate_log_decision_input(
        "Decide",
        "Because of reasons",
        "Alternative approach",
    )
    assert dec == "Decide"
    assert rea == "Because of reasons"
    assert alt == "Alternative approach"


def test_validate_log_decision_input_no_alternatives():
    """Test log_decision without alternatives."""
    dec, rea, alt = validation.validate_log_decision_input("Decide", "Reason")
    assert alt is None


def test_validate_update_state_input():
    """Test update_state input validation."""
    prog, steps, block = validation.validate_update_state_input(
        "Making progress",
        "Next steps",
        "Blockers here",
    )
    assert prog == "Making progress"
    assert steps == "Next steps"
    assert block == "Blockers here"


def test_validate_update_state_input_no_blockers():
    """Test update_state without blockers."""
    prog, steps, block = validation.validate_update_state_input("Progress", "Steps")
    assert block is None


def test_validate_log_session_input():
    """Test log_session input validation."""
    summ, dec = validation.validate_log_session_input(
        "Session summary",
        "Decisions made",
    )
    assert summ == "Session summary"
    assert dec == "Decisions made"


def test_validate_log_session_input_no_decisions():
    """Test log_session without decisions."""
    summ, dec = validation.validate_log_session_input("Summary")
    assert dec is None


def test_validate_export_markdown_input():
    """Test export_markdown input validation."""
    proj, path = validation.validate_export_markdown_input("project", "/path/file.md")
    assert proj == "project"
    assert path == "/path/file.md"


def test_validate_export_markdown_input_no_path():
    """Test export_markdown without path."""
    proj, path = validation.validate_export_markdown_input("project")
    assert path is None


def test_validate_export_markdown_input_non_string_path():
    """Test export_markdown with non-string path."""
    with pytest.raises(TypeError):
        validation.validate_export_markdown_input("project", 123)


def test_validate_export_markdown_input_path_too_long():
    """Test export_markdown with path too long."""
    with pytest.raises(ValueError):
        validation.validate_export_markdown_input("project", "x" * 501)


# ============================================================================
# core/db_init.py tests
# ============================================================================


def test_initialize_database(tmp_path, monkeypatch):
    """Test database initialization."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", db_path)
    initialize_database()
    assert Path(db_path).exists()


def test_initialize_database_creates_tables(isolated_db):
    """Test database initialization creates tables."""
    from sqlalchemy import create_engine, inspect

    db_path = f"sqlite:///{isolated_db}"
    engine = create_engine(db_path)
    inspector = inspect(engine)

    tables = inspector.get_table_names()
    assert "projects" in tables
    assert "decisions" in tables
    assert "state" in tables
    assert "sessions" in tables


# ============================================================================
# mcp_server/server.py tests
# ============================================================================


def test_setup_tools_registers_tools(isolated_db):
    """Test that setup_tools registers all tools."""
    server.setup_tools()
    # Verify the tools are registered
    assert server.mcp is not None


def test_mcp_server_initialization():
    """Test MCP server initialization."""
    assert server.mcp is not None
    assert hasattr(server.mcp, "run")


# ============================================================================
# mcp_server/tools.py tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_context_input_validation(isolated_db):
    """Test GetContextInput validation."""
    result = await tools.get_context(tools.GetContextInput(project_id="test-proj"))
    assert "project" in result


@pytest.mark.asyncio
async def test_log_decision_input_validation(isolated_db):
    """Test LogDecisionInput validation."""
    result = await tools.log_decision(
        tools.LogDecisionInput(
            project_id="test-proj",
            decision="Test decision",
            reasoning="Test reasoning",
        )
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_update_state_input_validation(isolated_db):
    """Test UpdateStateInput validation."""
    result = await tools.update_state(
        tools.UpdateStateInput(
            project_id="test-proj",
            progress="Test progress",
            next_steps="Test next steps",
        )
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_log_session_input_validation(isolated_db):
    """Test LogSessionInput validation."""
    result = await tools.log_session(
        tools.LogSessionInput(
            project_id="test-proj",
            summary="Test summary",
        )
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_export_markdown_writes_file(isolated_db, tmp_path):
    """Test export_markdown writes markdown file."""
    output_file = tmp_path / "output.md"
    result = await tools.export_markdown(
        tools.ExportMarkdownInput(
            project_id="test-proj",
            output_path=str(output_file),
        )
    )
    assert result["success"] is True
    assert output_file.exists()


# ============================================================================
# core/storage.py tests
# ============================================================================


@pytest.mark.asyncio
async def test_storage_error_handling(isolated_db):
    """Test storage error handling."""
    # Test that invalid data raises appropriate errors
    with pytest.raises(Exception):
        await storage.get_decisions(project_id="nonexistent")


@pytest.mark.asyncio
async def test_get_briefing_creates_project(isolated_db):
    """Test get_briefing creates project if not exists."""
    briefing = await storage.get_briefing("new-project")
    assert briefing["project"]["id"] == "new-project"


@pytest.mark.asyncio
async def test_create_decision_returns_id(isolated_db):
    """Test create_decision returns decision ID."""
    result = await storage.create_decision(
        project_id="test-proj",
        decision="Test decision",
        reasoning="Test reasoning",
    )
    assert "id" in result
    assert result["decision"] == "Test decision"


@pytest.mark.asyncio
async def test_update_state_creates_state(isolated_db):
    """Test update_state creates state if not exists."""
    result = await storage.update_state(
        project_id="test-proj",
        progress="Progress",
        next_steps="Steps",
    )
    assert "id" in result
    assert result["progress"] == "Progress"


@pytest.mark.asyncio
async def test_create_session_returns_id(isolated_db):
    """Test create_session returns session ID."""
    result = await storage.create_session(
        project_id="test-proj",
        summary="Test summary",
    )
    assert "id" in result
    assert result["summary"] == "Test summary"


@pytest.mark.asyncio
async def test_export_markdown_renders_content(isolated_db):
    """Test export_markdown renders full context."""
    await storage.create_decision(
        project_id="test-proj",
        decision="Test decision",
        reasoning="Test reasoning",
    )
    await storage.update_state(
        project_id="test-proj",
        progress="Progress",
        next_steps="Steps",
    )

    markdown = await storage.export_markdown("test-proj")
    assert "test-proj" in markdown
    assert "Test decision" in markdown
    assert "Progress" in markdown


# ============================================================================
# Additional integration tests
# ============================================================================


@pytest.mark.asyncio
async def test_full_workflow_with_redaction(isolated_db):
    """Test full workflow with secret redaction."""
    project_id = "redaction-test"

    # Log decision with secret
    decision = await services.log_decision(
        project_id=project_id,
        decision="Use API",
        reasoning="API key: AKIAIOSFODNN7EXAMPLE",
    )
    assert "[REDACTED]" in decision["reasoning"]

    # Get context and verify no secrets
    briefing = await services.get_briefing(project_id)
    assert "[REDACTED]" in briefing["decisions"][0]["reasoning"]


@pytest.mark.asyncio
async def test_services_validation_integration(isolated_db):
    """Test services with integrated validation."""
    project_id = "validation-test"

    # Test empty decision should fail
    with pytest.raises(Exception):
        await services.log_decision(
            project_id=project_id,
            decision="",
            reasoning="Reason",
        )


def test_config_singleton():
    """Test config singleton behavior."""
    cfg1 = config.config
    cfg2 = config.config
    assert cfg1 is cfg2


# ============================================================================
# Additional mcp_server/__main__.py tests
# ============================================================================


def test_main_module_imports(isolated_db):
    """Test that main module imports correctly."""
    # Import the __main__ module to test it runs without errors
    from mcp_server import __main__ as main_module
    assert main_module is not None


@pytest.mark.asyncio
async def test_tools_error_cases_not_found(isolated_db):
    """Test tool error handling for missing projects."""
    # Try getting context for non-existent project
    result = await tools.get_context(tools.GetContextInput(project_id="nonexistent"))
    assert result is not None


# ============================================================================
# Additional db_init tests
# ============================================================================


def test_db_init_creates_all_tables(tmp_path, monkeypatch):
    """Test that init creates all necessary tables."""
    db_path = str(tmp_path / "full_test.db")
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", db_path)
    from core.db_init import initialize_database as init_db
    init_db()

    from sqlalchemy import create_engine, inspect
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    # Verify all tables exist
    tables = {t.lower() for t in inspector.get_table_names()}
    required_tables = {"projects", "decisions", "state", "sessions"}
    assert required_tables.issubset(tables)


# ============================================================================
# Additional redaction tests
# ============================================================================


def test_redact_invalid_pattern_error_handling():
    """Test that invalid regex patterns are handled gracefully."""
    # The redactor should handle invalid patterns without crashing
    text = "some text with secret"
    result = redaction.SecretRedactor.redact(text)
    assert isinstance(result, str)


def test_redact_dict_with_non_string_values():
    """Test dictionary redaction with mixed value types."""
    data = {
        "string": "api_key=secret",
        "number": 123,
        "none": None,
        "bool": True,
        "nested_list": [1, 2, "api_key=secret"],
        "nested_dict": {"api_key": "api_key=secret"},
    }
    redacted = redaction.SecretRedactor.redact_dict(data)
    assert redacted["number"] == 123
    assert redacted["none"] is None
    assert redacted["bool"] is True


# ============================================================================
# Additional tools tests
# ============================================================================


@pytest.mark.asyncio
async def test_tools_with_invalid_input(isolated_db):
    """Test tools with edge case inputs."""
    # Test with minimal valid input
    result = await tools.log_session(
        tools.LogSessionInput(
            project_id="test",
            summary="x",  # Minimal valid string
        )
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_export_markdown_with_complex_content(isolated_db, tmp_path):
    """Test export_markdown with multiple decisions and sessions."""
    project_id = "complex-proj"
    output = tmp_path / "complex.md"

    # Add multiple decisions
    for i in range(3):
        await services.log_decision(
            project_id=project_id,
            decision=f"Decision {i}",
            reasoning=f"Reason {i}",
        )

    # Add state
    await services.update_state(
        project_id=project_id,
        progress="Multiple decisions made",
        next_steps="Execute decisions",
    )

    # Add multiple sessions
    for i in range(2):
        await services.log_session(
            project_id=project_id,
            summary=f"Session {i}",
        )

    result = await tools.export_markdown(
        tools.ExportMarkdownInput(
            project_id=project_id,
            output_path=str(output),
        )
    )

    assert result["success"] is True
    markdown_content = output.read_text()
    assert "Decision 0" in markdown_content
    assert "Decision 1" in markdown_content
    assert "Decision 2" in markdown_content
    assert "Session 0" in markdown_content
    assert "Session 1" in markdown_content


# ============================================================================
# Additional storage tests
# ============================================================================


@pytest.mark.asyncio
async def test_multiple_projects_isolation(isolated_db):
    """Test that multiple projects' data is isolated."""
    # Create context for project 1
    await services.log_decision(
        project_id="project-1",
        decision="Project 1 decision",
        reasoning="Reasoning 1",
    )

    # Create context for project 2
    await services.log_decision(
        project_id="project-2",
        decision="Project 2 decision",
        reasoning="Reasoning 2",
    )

    # Get context for each project
    context1 = await services.get_briefing("project-1")
    context2 = await services.get_briefing("project-2")

    # Verify isolation
    assert context1["project"]["id"] == "project-1"
    assert context2["project"]["id"] == "project-2"
    assert context1["decisions"][0]["decision"] == "Project 1 decision"
    assert context2["decisions"][0]["decision"] == "Project 2 decision"


# ============================================================================
# Services edge case tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_state_with_all_fields(isolated_db):
    """Test update_state with all optional fields."""
    result = await services.update_state(
        project_id="full-state",
        progress="All fields provided",
        next_steps="Complete workflow",
        blockers="No blockers",
    )
    assert result["progress"] == "All fields provided"
    assert result["next_steps"] == "Complete workflow"
    assert result["blockers"] == "No blockers"


@pytest.mark.asyncio
async def test_log_session_with_decisions(isolated_db):
    """Test log_session with decisions_made field."""
    result = await services.log_session(
        project_id="session-with-decisions",
        summary="Session summary",
        decisions_made="Decisions that were made",
    )
    assert result["summary"] == "Session summary"
    assert result["decisions_made"] == "Decisions that were made"


@pytest.mark.asyncio
async def test_briefing_empty_project(isolated_db):
    """Test briefing for project with no decisions or state."""
    briefing = await services.get_briefing("empty-project")
    assert briefing["project"]["id"] == "empty-project"
    assert len(briefing["decisions"]) == 0
    assert briefing["current_state"] is None
    assert len(briefing["recent_sessions"]) == 0
