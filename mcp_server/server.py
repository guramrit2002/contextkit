"""FastMCP server for contextkit. Importing this module gives a ready server (ADR 026)."""
import logging

from fastmcp import FastMCP

from core.config import config
from core.db_init import UPGRADE_COMMAND, core_schema_status

logger = logging.getLogger(__name__)

INSTRUCTIONS = "\n".join([
    "contextkit stores this project's shared context so AI agents can hand work to each other.",
    "",
    "- At the start of a task, call get_context to load the project briefing: decisions, "
    "current state, and recent sessions.",
    "- While working, call log_decision when you make a meaningful decision (with its "
    "reasoning), and update_state when progress, next steps, or blockers change.",
    "- Before finishing, call log_session with a summary of what you did.",
])

mcp = FastMCP("contextkit", instructions=INSTRUCTIONS)

_tools_registered = False


def setup_tools():
    """Register the 5 contextkit tools. Safe to call more than once."""
    global _tools_registered
    if _tools_registered:
        return
    from . import tools

    mcp.tool(tools.get_context_flat, name="get_context")
    mcp.tool(tools.log_decision)
    mcp.tool(tools.update_state)
    mcp.tool(tools.log_session)
    mcp.tool(tools.export_markdown_flat, name="export_markdown")
    _tools_registered = True
    logger.info("Registered 5 contextkit tools")


def check_hosted_schema():
    """
    Hosted servers never migrate on start (replicas would race); migrations are a deploy step.
    Refuse to start if the database is behind the code.
    """
    if not config.is_hosted():
        return
    status = core_schema_status()
    if not status.up_to_date:
        raise RuntimeError(
            f"Core database is at migration {status.current or 'none'}, but this server needs "
            f"{status.head}. Run `{UPGRADE_COMMAND}` with DATABASE_URL set, then redeploy."
        )


setup_tools()
check_hosted_schema()
