# ADR 018 — Briefing token budget

**Status:** Open

## Context

`get_context` returns a briefing to the agent. If the briefing is too large, it consumes most of the agent's context window, leaving little room for code. A hard cap is needed.

## Decision

Not yet made.

## Open questions

- What is the default token budget? (4,000 tokens is a reasonable starting point.)
- Should it be configurable per project or per user?
- Dropping order when over budget: oldest sessions first, then oldest decisions. Stable context and current state are never dropped. Is this the right priority?
- How are tokens counted: character approximation or a tokenizer?
