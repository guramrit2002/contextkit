import pytest

from core import storage
from mcp_server import tools
from mcp_server.server import mcp, setup_tools


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTKIT_DB_PATH", str(tmp_path / "contextkit.sqlite3"))
    storage.init_db()


@pytest.mark.asyncio
async def test_mcp_tool_wrappers_round_trip_context(isolated_db):
    project_id = "tool-project"

    decision_result = await tools.log_decision(
        tools.LogDecisionInput(
            project_id=project_id,
            decision="Expose a thin MCP layer",
            reasoning="Business logic belongs in core services",
        )
    )
    state_result = await tools.update_state(
        tools.UpdateStateInput(
            project_id=project_id,
            progress="Tool wrappers added",
            next_steps="Run the MCP server",
        )
    )
    session_result = await tools.log_session(
        tools.LogSessionInput(
            project_id=project_id,
            summary="Exercised MCP wrappers",
        )
    )
    context = await tools.get_context(tools.GetContextInput(project_id=project_id))

    assert decision_result["success"] is True
    assert state_result == {"success": True}
    assert session_result["success"] is True
    assert context["project"]["id"] == project_id
    assert context["decisions"][0]["decision"] == "Expose a thin MCP layer"
    assert context["current_state"]["next_steps"] == "Run the MCP server"
    assert context["recent_sessions"][0]["summary"] == "Exercised MCP wrappers"


@pytest.mark.asyncio
async def test_export_markdown_writes_requested_file(isolated_db, tmp_path):
    project_id = "export-project"
    output_path = tmp_path / "exports" / "context.md"
    await tools.update_state(
        tools.UpdateStateInput(
            project_id=project_id,
            progress="Ready to export",
            next_steps="Share context",
        )
    )

    result = await tools.export_markdown(
        tools.ExportMarkdownInput(project_id=project_id, output_path=str(output_path))
    )

    assert result["success"] is True
    assert output_path.read_text(encoding="utf-8") == result["markdown"]
    assert "Ready to export" in result["markdown"]


@pytest.mark.asyncio
async def test_registered_export_markdown_uses_flat_arguments(isolated_db, tmp_path):
    setup_tools()
    output_path = tmp_path / "context.md"

    result = await mcp.call_tool(
        "export_markdown",
        {
            "project_id": "inspector-project",
            "output_path": str(output_path),
        },
    )

    assert result.is_error is False
    assert output_path.exists()


@pytest.mark.asyncio
async def test_registered_export_markdown_accepts_nested_input_arguments(isolated_db, tmp_path):
    setup_tools()
    output_path = tmp_path / "nested-context.md"

    result = await mcp.call_tool(
        "export_markdown",
        {
            "input": {
                "project_id": "inspector-project",
                "output_path": str(output_path),
            },
        },
    )

    assert result.is_error is False
    assert output_path.exists()
