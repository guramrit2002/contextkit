# ADR 006 — MVT applies to Django only

**Status:** Accepted

## Context

The project uses Django, which follows the Model-View-Template pattern. It would be a mistake to apply that pattern to core or the MCP server, which are not web applications.

## Decision

MVT applies only inside `backend/`. Core is a service layer with modules organized by responsibility. The MCP server is a transport layer organized by tool.

## Consequences

- Core modules are named for what they do: `briefing.py`, `compaction.py`, `redaction.py`.
- The MCP server has `tools.py`, `context.py`, `rendering.py`.
- No views, templates, or Django models appear outside `backend/`.
