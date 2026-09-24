import pytest

from core import services, storage


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(tmp_path / "contextkit.sqlite3"))
    storage.init_db()


@pytest.mark.asyncio
async def test_project_briefing_includes_state_decisions_and_recent_sessions(isolated_db):
    project_id = "test-project"

    decision = await services.log_decision(
        project_id=project_id,
        decision="Use SQLite first",
        reasoning="It keeps local setup simple",
        alternatives_considered="PostgreSQL",
    )
    state = await services.update_state(
        project_id=project_id,
        progress="Storage is implemented",
        next_steps="Add MCP tests",
        blockers=None,
    )
    session = await services.log_session(
        project_id=project_id,
        summary="Built the storage layer",
        decisions_made="Kept the MCP layer thin",
    )

    briefing = await services.get_briefing(project_id)

    assert briefing["project"]["id"] == project_id
    assert briefing["decisions"] == [
        {
            "id": decision["id"],
            "decision": "Use SQLite first",
            "reasoning": "It keeps local setup simple",
            "alternatives_considered": "PostgreSQL",
            "created_at": decision["created_at"],
        }
    ]
    assert briefing["current_state"]["id"] == state["id"]
    assert briefing["current_state"]["progress"] == "Storage is implemented"
    assert briefing["recent_sessions"] == [
        {
            "id": session["id"],
            "project_id": project_id,
            "summary": "Built the storage layer",
            "decisions_made": "Kept the MCP layer thin",
            "created_at": session["created_at"],
        }
    ]


@pytest.mark.asyncio
async def test_export_markdown_renders_full_context(isolated_db):
    project_id = "markdown-project"
    await services.log_decision(
        project_id=project_id,
        decision="Keep core plain Python",
        reasoning="Multiple transports can reuse it",
    )
    await services.update_state(
        project_id=project_id,
        progress="Core service exists",
        next_steps="Expose it through MCP",
        blockers="None",
    )
    await services.log_session(
        project_id=project_id,
        summary="Added service functions",
    )

    markdown = await services.export_markdown(project_id)

    assert "# Project Context: markdown-project" in markdown
    assert "**Progress:**\nCore service exists" in markdown
    assert "**What:** Keep core plain Python" in markdown
    assert "Added service functions" in markdown
