# ADR 011 — Pydantic for schemas and validation

**Status:** Proposed

## Context

Tool inputs need validation. Domain objects need a consistent structure. FastMCP integrates well with Pydantic and generates tool schemas from it automatically.

## Decision

Use Pydantic v2 for all input schemas, output models, and domain objects in core. FastMCP reads these to generate MCP tool schemas.

## Consequences

- Tool schemas are derived from code, not maintained separately.
- Validation errors are consistent across all tools.
- Pydantic models serve as the contract between transports and core.
