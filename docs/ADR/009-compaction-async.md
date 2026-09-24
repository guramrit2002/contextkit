# ADR 009 — Compaction runs asynchronously

**Status:** Accepted

## Context

Compaction calls an LLM to summarize sessions. LLM calls are slow (seconds to tens of seconds). An agent calling `log_session` should not wait for summarization to complete.

## Decision

Compaction runs asynchronously. `log_session` saves the raw session immediately and returns. Compaction is triggered separately, either by a session-count threshold, a schedule, or a manual call to `run_compaction`.

## Consequences

- Agent calls are fast and never blocked by LLM latency.
- If compaction fails, the raw sessions are untouched and retried on the next trigger.
- The `compacted` flag on sessions tracks which have been processed.
- The trigger mechanism (threshold, schedule, or manual) is configurable.
