# ADR 016 — LLM for compaction summarization

**Status:** Open

## Context

Compaction uses an LLM to summarize sessions into decisions and updated state. The provider, model, and trigger need to be chosen.

## Options

| Option | Trade-off |
|---|---|
| Anthropic Claude (user's own key) | Familiar, good at structured output, costs per call |
| OpenAI GPT-4o (user's own key) | Widely available, good structured output |
| Local model via Ollama | Free, private, slower and less capable |
| Provider-agnostic via config | Most flexible, more code to write |

## Decision

Not yet made.

## Open questions

- Which provider and model?
- What triggers compaction: session count, a schedule, or manual only?
- What is the structured output format the LLM should return?
