# ADR 017 — Secret redaction approach

**Status:** Accepted

## Context

Agent sessions can contain API keys, tokens, passwords, and other secrets. These must be removed before storage and before any text is sent to an LLM.

## Options

| Option | Trade-off |
|---|---|
| Regex patterns | Simple, fast, misses unusual formats |
| `detect-secrets` library | Broader coverage, adds a dependency |
| Both (regex first, detect-secrets for edge cases) | Best coverage, more complex |

## Decision

**Phase 1: Regex patterns only** (now)

Use the existing `SecretRedactor` class with regex patterns for common formats:
- API keys and tokens (`api_key=`, `token=`, `secret=`)
- AWS keys (`AKIA...`, `aws_secret_access_key=`)
- GitHub tokens (`gh_`, `ghp_`, `ghu_`, `ghs_`, `ghr_`)
- URL credentials (`https://user:password@host`)
- SSH/PEM private keys (`-----BEGIN ... PRIVATE KEY-----`)

**Phase 2: Add `detect-secrets` library** (later, follow-up ADR)

Once Phase 1 is stable, add `detect-secrets` for deeper entropy-based scanning. This catches edge cases regex misses (unusual formats, non-standard configs).

Redaction flow in Phase 2:
```
text → regex pass (fast) → if still suspicious → detect-secrets pass (deep) → redacted text
```

## Consequences

**Phase 1:**
- ✅ No new dependencies; uses only `re` module
- ✅ Fast; runs once per tool call
- ✅ Already implemented and tested
- ✅ Catches ~80% of common secrets in agent logs
- ⚠️ May miss edge cases (unusual formats, malformed URLs, etc.)

**Phase 2 (deferred):**
- Will improve coverage to ~95%+
- Adds `detect-secrets` dependency
- Slight performance cost (two-pass scan)

## Open questions

- What's the tolerance for false negatives in Phase 1? (Is 80% coverage acceptable, or do we need Phase 2 now?)
- Should redaction placeholder be `[REDACTED]` or `[REDACTED:secret_type]`? (Keeping `[REDACTED]` for simplicity.)
- Should audit_log record when redaction occurred (for debugging)?
