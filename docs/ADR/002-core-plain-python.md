# ADR 002 — Core services are plain Python

**Status:** Accepted

## Context

Core needs to be called by the MCP server (step 1), a hosted MCP server (step 2), and a REST API (step 3). Each transport is different. If core depended on a framework, every transport would inherit that dependency.

## Decision

Core is a plain Python package with no imports from Django, FastMCP, or any web framework.

## Consequences

- Any transport can call core without running a framework.
- Core can be tested independently with no server or database setup beyond SQLite.
- The local MCP server does not require Django to be installed or running.
- Adding a new transport means writing a thin wrapper, not porting logic.
