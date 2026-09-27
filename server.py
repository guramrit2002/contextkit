"""Horizon entrypoint: `server.py:mcp`. Loads the package so its relative imports work."""
from mcp_server.server import mcp

__all__ = ["mcp"]
