# ADR 020 — API key authentication issued by Django

**Status:** Proposed

## Context

The hosted MCP server needs to authenticate agents and identify which user each request belongs to. Django already manages users and is the natural place to issue credentials.

## Decision

Django issues API keys during onboarding. The MCP server validates each hosted request by hashing the incoming key and looking it up in the `api_keys` table. A valid key resolves to a `user_id`. Django is the sole writer of the `api_keys` table; the MCP server only reads it.

Only the hash of a key is stored. The plaintext key is shown to the user once at creation.

## Consequences

- Revoking a key in Django immediately blocks the corresponding agent.
- The MCP server has a read dependency on Django's `api_keys` table.
- Local mode (step 1) has no authentication; `user_id` comes from config.
