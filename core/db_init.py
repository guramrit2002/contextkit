"""Initialize the database with tables."""
import logging

from core.storage import init_db

logger = logging.getLogger(__name__)


def initialize_database():
    """Create all database tables."""
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
