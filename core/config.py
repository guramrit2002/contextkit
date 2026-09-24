"""Configuration management for contextkit."""
import os
from typing import Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """Application configuration loaded from environment variables."""

    # Core settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEFAULT_USER_ID: str = os.getenv("DEFAULT_USER_ID", "default_user")

    # Database configuration
    CONTEXTKIT_DB_PATH: Optional[str] = os.getenv("CONTEXTKIT_DB_PATH")

    # MCP server configuration
    MCP_HOST: str = os.getenv("MCP_HOST", "localhost")
    MCP_PORT: int = int(os.getenv("MCP_PORT", "5000"))

    # Feature flags
    ENABLE_SESSION_COMPACTION: bool = (
        os.getenv("ENABLE_SESSION_COMPACTION", "False").lower() == "true"
    )
    MAX_BRIEFING_TOKENS: int = int(os.getenv("MAX_BRIEFING_TOKENS", "4000"))
    ENABLE_REDACTION: bool = os.getenv("ENABLE_REDACTION", "True").lower() == "true"

    # Django settings (for Step 2+)
    DJANGO_SECRET_KEY: str = os.getenv("DJANGO_SECRET_KEY", "")
    DJANGO_DEBUG: bool = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
    DJANGO_ALLOWED_HOSTS: list = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

    @classmethod
    def get_default_user_id(cls) -> str:
        """Get the default user ID for single-user mode."""
        return cls.DEFAULT_USER_ID

    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development mode."""
        return cls.ENVIRONMENT.lower() in ["development", "dev", "local"]

    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production mode."""
        return cls.ENVIRONMENT.lower() == "production"

    @classmethod
    def get_db_path(cls) -> Optional[str]:
        """Get database path if configured."""
        return cls.CONTEXTKIT_DB_PATH


# Create a singleton instance
config = Config()
