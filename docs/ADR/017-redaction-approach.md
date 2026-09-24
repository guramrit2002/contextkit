# ADR 017 — Secret redaction approach

**Status:** Open

## Context

Agent sessions can contain API keys, tokens, passwords, and other secrets. These must be removed before storage and before any text is sent to an LLM.

## Options

| Option | Trade-off |
|---|---|
| Regex patterns | Simple, fast, misses unusual formats |
| `detect-secrets` library | Broader coverage, adds a dependency |
| Both (regex first, detect-secrets for edge cases) | Best coverage, more complex |

## Decision

Not yet made.

## Open questions

- Which secret formats are most common in agent sessions (API keys, `.env` assignments, connection strings)?
- What should the placeholder look like: `[REDACTED]`, `[REDACTED:api_key]`, or something else?
- Should redaction be configurable per user?
