# contextkit — agent instructions

Read this file before starting any task. Read the architecture documents listed below before writing any code.

---

## What this project is

contextkit is an MCP server that stores project context so AI agents can hand off work to each other without a human writing a handoff document. Agents call `get_context` when they start and `log_session` before they finish. When you switch from one agent to another, the next one picks up where the last one stopped.

## Architecture documents

Read these before touching any code:

- [`ARCHITECTURE.md`](docs/Architecture/ARCHITECTURE.md) — system overview, layering rules, data flow
- [`core/ARCHITECTURE.md`](docs/Architecture/core/ARCHITECTURE.md) — core services detail
- [`mcp_server/ARCHITECTURE.md`](docs/Architecture/mcp_server/ARCHITECTURE.md) — MCP server detail
- [`backend/ARCHITECTURE.md`](docs/Architecture/backend/ARCHITECTURE.md) — Django backend detail
- [`docs/adr/`](docs/ADR) — all architecture decisions

## Component map

```
contextkit/
├── core/            # plain Python, no framework imports — all logic lives here
├── mcp_server/      # FastMCP, thin wrappers only — no logic
├── backend/         # Django — onboarding and analytics only
├── docs/adr/        # architecture decision records
└── tests/
```

## Rules that must not be broken

1. **Core has no framework imports.** Never import Django or FastMCP inside `core/`.
2. **Transports are thin.** Each MCP tool calls exactly one `core.services` function. No logic in `mcp_server/`.
3. **Only core writes context tables.** `projects`, `decisions`, `state`, `sessions` are written exclusively through `core.storage`.
4. **Django never sits on the write path.** Agent requests must not depend on Django being available.
5. **MVT applies only to Django.** Core is a service layer, not MVT.
6. **Business logic belongs in `services.py`.** Not in views, not in models.

## Tech stack

| Component | Technology |
|---|---|
| MCP server | Python 3.12, FastMCP |
| Core | Plain Python, Pydantic, SQLAlchemy, Alembic |
| Database | SQLite locally (`~/.contextkit/contextkit.db`) |
| Django | Django + DRF (not active in step 1) |
| Package manager | uv |
| Tests | pytest |

## Current status

Step 1: single-user local MCP server. Django is not running. There is no authentication. The `user_id` is a fixed value from config.

The five MCP tools are:

| Tool | Purpose |
|---|---|
| `get_context` | Load the project briefing at the start of a task |
| `log_decision` | Record a decision and its rationale |
| `update_state` | Replace the current state with progress, next steps, and blockers |
| `log_session` | Append a session summary before finishing |
| `export_markdown` | Export the full context as a markdown file |

## Before you start a task
Call get_context from the contextkit MCP server.
Read the relevant architecture document for the component you are working in.
Check docs/adr/ for any open decisions that affect the task.

## Before you finish a task
Call update_state with what is done, what is next, and any blockers.
Call log_session with a summary of what was built or changed.
If a meaningful decision was made during the task, call log_decision with the reasoning.

## Key decisions (summary)

Full reasoning is in `docs/adr/`. Short version:

- SQLAlchemy over raw sqlite3 so the move to Postgres is a config change
- Pydantic for all schemas and tool inputs
- Project identified from git remote URL, falling back to folder path
- `user_id` on every record from day one, hardcoded for now
- Alembic manages core table migrations; Django migrations never touch them
- Compaction runs async after sessions are saved, never blocking an agent call
- Secrets redacted before storage and before any LLM summarization call
- Briefing has a hard token budget; oldest sessions dropped first if over budget

## What not to do

- Do not add logic to `mcp_server/tools.py` beyond input validation and forwarding
- Do not import `core.storage` or `core.models` outside of `core/`
- Do not run Django migrations against the context tables
- Do not let compaction block a tool response
- Do not store text before redaction has run