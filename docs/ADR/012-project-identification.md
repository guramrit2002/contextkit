# ADR 012 — Project identified from git remote URL

**Status:** Proposed

## Context

Agents run inside a project directory. The MCP server needs to know which project a request belongs to without the agent or user specifying it manually each time.

## Decision

Core resolves the project by reading the git remote URL of the repository the MCP server was launched from, normalized by stripping protocol, credentials, and `.git`. If no git remote is found, the absolute folder path is used as the identifier. An explicit `project_hint` argument overrides both.

## Consequences

- Agents do not need to pass a project name on every call.
- The same project is identified consistently across machines if the git remote matches.
- Projects without a git remote use the folder path, which may differ between machines.
- The normalization logic must be tested for common remote formats (HTTPS, SSH, various hosts).
