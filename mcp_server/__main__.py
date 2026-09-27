"""Run the contextkit MCP server locally over stdio."""
import logging

from core.db_init import initialize_database

from .server import mcp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # Local mode migrates its own SQLite database on start; hosted mode migrates at deploy.
    try:
        initialize_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    logger.info("Starting contextkit MCP server")
    mcp.run()
