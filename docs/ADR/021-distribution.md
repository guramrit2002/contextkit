# ADR 021 — Distribution

**Status:** Open

## Context

Other developers need to be able to install and run the local MCP server easily. The project should be findable and installable without cloning the repository.

## Options

| Option | Trade-off |
|---|---|
| PyPI + `uvx contextkit` | One command, no clone needed, standard Python |
| PyPI + `pipx install contextkit` | Similar, broader familiarity |
| GitHub only | No publishing step, friction for new users |
| Homebrew | macOS/Linux friendly, extra maintenance |

## Decision

Not yet made.

## Open questions

- What is the package and command name? (`contextkit`, `ck`, or something else?)
- What license? MIT is the default assumption for open source.
- When is the first public release — after step 1 is stable, or after step 2?
