# ADR 015 — Local storage at ~/.contextkit/

**Status:** Proposed

## Context

The local MCP server needs a place to store the database and config file that is outside any project repository (so it is not accidentally committed) and consistent across projects.

## Decision

All local data is stored in `~/.contextkit/`:

```
~/.contextkit/
├── contextkit.db    # SQLite database
└── config.toml      # user_id, LLM provider, API key, compaction settings
```

## Consequences

- One database holds all projects for the local user.
- The location is predictable and easy to back up or inspect.
- Moving to a hosted deployment means pointing to a Postgres URL in config instead.
