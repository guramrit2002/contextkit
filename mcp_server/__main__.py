"""Run the contextkit MCP server."""
import logging

from core.db_init import initialize_database

from .server import mcp, setup_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # Initialize database
    try:
        initialize_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    setup_tools()
    logger.info("Starting contextkit MCP server")
    mcp.run()
