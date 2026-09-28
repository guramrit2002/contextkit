"""Hosted entrypoint (`server.py:mcp`), e.g. `fastmcp run server.py:mcp --transport http`.

Imports the package so its relative imports work.
"""
from mcp_server.server import mcp

__all__ = ["mcp"]
