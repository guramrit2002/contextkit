# ADR 005 — Monorepo structure

**Status:** Accepted

## Context

contextkit has three components: core, the MCP server, and the Django backend. They share domain types and are developed together. Separate repositories would add friction for a small project.

## Decision

All components live in a single repository under `core/`, `mcp_server/`, and `backend/`.

## Consequences

- Domain types and schemas are imported directly from `core` without publishing a package.
- A single `uv` workspace manages dependencies for all components.
- A single test run covers all components.
- When core changes, MCP server and Django changes can be committed atomically.
