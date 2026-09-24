# ADR 014 — Python 3.12, uv, pytest, MCP Inspector

**Status:** Proposed

## Context

The project needs a Python version, a package manager, a test runner, and a way to manually test MCP tools during development.

## Decision

- **Python 3.12** — current stable release with good typing support.
- **uv** — fast dependency management and script running; replaces pip and virtualenv.
- **pytest** — standard test runner with a rich plugin ecosystem.
- **MCP Inspector** — official MCP tool for manually testing tools over stdio: `npx @modelcontextprotocol/inspector`.

## Consequences

- `uv sync` sets up the environment from `pyproject.toml`.
- `uv run pytest` runs the test suite.
- MCP Inspector allows testing tool inputs and outputs without a connected agent.
