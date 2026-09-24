"""FastMCP server for contextkit."""
import logging
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("contextkit")


def setup_tools():
    """Register all MCP tools."""
    from . import tools

    # Import tool functions to register them
    mcp.tool(tools.get_context_flat, name="get_context")
    mcp.tool(tools.log_decision)
    mcp.tool(tools.update_state)
    mcp.tool(tools.log_session)
    mcp.tool(tools.export_markdown_flat, name="export_markdown")

    logger.info("Registered 5 contextkit tools")


if __name__ == "__main__":
    setup_tools()
    # Server will be run via FastMCP's built-in server
