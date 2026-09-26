# Project Context: contextkit.git

**Project ID:** `https://github.com/guramrit2002/contextkit.git`

**Git Remote:** https://github.com/guramrit2002/contextkit.git

## Current State

**Progress:**
Added pytest coverage for core services and MCP tool wrappers. get_context now includes recent_sessions, storage supports CONTEXTKIT_DB_PATH for isolated tests, SQLite engines are disposed/NullPool-backed to avoid unclosed connection warnings, timestamps use timezone-aware UTC, and export_markdown creates parent directories with explicit write errors.

**Next Steps:**
Add tests for server registration/startup behavior and negative/error paths such as invalid export locations or missing database initialization. Then align default storage location with the README's ~/.contextkit claim or update the documentation.

**Blockers:**
uv is not installed locally; pytest dependencies were installed directly into .venv with pip for verification.

## Decisions

### Decision 1
**What:** Use SQLAlchemy for database access

**Why:** Enables easy migration to PostgreSQL later

**Alternatives:** Raw sqlite3 or Django ORM

*Recorded: 2026-09-23T18:15:20.371245*

### Decision 2
**What:** Use SQLAlchemy for database access

**Why:** Enables easy migration to PostgreSQL later

**Alternatives:** Raw sqlite3 or Django ORM

*Recorded: 2026-09-23T18:45:51.353131*

## Recent Sessions

### Session 1
Implemented SQLAlchemy models and storage layer for contextkit

**Decisions Made:** Chose to use async storage functions for future scalability

*Date: 2026-09-23T18:15:20.376286*

### Session 2
Implemented SQLAlchemy models and storage layer for contextkit

**Decisions Made:** Chose to use async storage functions for future scalability

*Date: 2026-09-23T18:45:51.360226*

### Session 3
Continued development from the saved state by adding real pytest coverage for the core service layer and MCP tool wrappers. Implemented isolated database configuration via CONTEXTKIT_DB_PATH, included recent_sessions in get_context responses, removed debug printing, hardened markdown export writes, switched SQLAlchemy SQLite engines to NullPool/dispose behavior, and replaced deprecated utcnow usage with timezone-aware UTC timestamps. Verified with compileall and pytest: 4 passed.

**Decisions Made:** Kept the MCP layer thin and tested it through its Pydantic input models; used an environment variable for test database isolation rather than adding a new configuration abstraction.

*Date: 2026-09-23T18:49:04.554628*

### Session 4
Adjusted MCP server registration for Inspector compatibility by exposing get_context and export_markdown with flat argument signatures while keeping the original Pydantic-wrapper functions available in Python. Verified export_markdown schema now has top-level project_id and output_path, and pytest passes with 5 tests.

**Decisions Made:** Use flat registered MCP tool signatures for Inspector-facing tools where nested Pydantic input objects caused -32602 invalid parameter errors.

*Date: 2026-09-23T18:55:35.673456*

