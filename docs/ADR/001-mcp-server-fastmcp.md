# ADR 001 — MCP server uses FastMCP

**Status:** Accepted

## Context

contextkit needs to expose tools to AI agents. The Model Context Protocol is the standard that Claude Code, Codex, and Cursor all support. An MCP server needs a Python library to handle the protocol.

## Decision

Use FastMCP as the MCP server library. The server is a thin transport layer with no business logic.

## Consequences

- Tool definitions are concise. FastMCP handles protocol framing, input parsing, and error serialization.
- Business logic stays in core, so switching MCP libraries later does not require rewriting logic.
- Each tool is a short function that calls one `core.services` function and returns its result.
