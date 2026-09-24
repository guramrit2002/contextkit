# ADR 019 — stdio locally, streamable HTTP when hosted

**Status:** Proposed

## Context

MCP supports multiple transports. The local tool is launched as a subprocess by each agent, which means stdio. The hosted service needs to handle multiple concurrent connections, which requires HTTP.

## Decision

- **Step 1 (local):** stdio transport. Each agent launches the server as a subprocess.
- **Step 2 (hosted):** streamable HTTP transport. The server runs as a long-lived service.

Tool definitions are identical in both modes. The transport is selected from config.

## Consequences

- No code changes to tools when switching transport.
- Agent MCP config differs: stdio uses a command, HTTP uses a URL and API key.
- The hosted server needs to handle connection lifecycle and concurrent requests.
