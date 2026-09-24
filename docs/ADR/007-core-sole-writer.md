# ADR 007 — Core is the sole writer of context tables

**Status:** Accepted

## Context

The context tables (projects, decisions, state, sessions) need a single owner to prevent conflicting writes, maintain invariants like redaction before storage, and keep the write path independent of Django.

## Decision

Only `core.storage` writes to the context tables. No other component, including Django and the REST API, writes to them directly. All writes go through `core.services`.

## Consequences

- Redaction, compaction triggers, and version checks run on every write without exception.
- Django reads context tables with `managed = False` models and never writes them.
- The REST API (step 3) calls `core.services` functions, same as the MCP server.
- Testing the write path means testing core, not each transport separately.
