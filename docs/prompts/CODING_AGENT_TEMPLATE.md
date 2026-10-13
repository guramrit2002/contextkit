# Coding Agent Prompt Template

**Purpose:** Reusable prompt to hand a spec off to a coding agent for implementation.

Copy the block below, fill in the `<...>` placeholders, and give it to a fresh coding session.

---

## Prompt

```
You are implementing a feature for contextkit based on a written spec. Read
everything below before writing any code.

## 1. Your spec

Read `docs/spec/<SPEC_FILE>.md` in full. That file is the source of truth for
what to build: endpoints/functions, schemas, request/response shapes, and the
implementation checklist.

If a matching prompt file exists at `docs/prompts/<PROMPT_FILE>.md`, read that
too — it narrows the spec down to your specific task and lists exactly which
files to create or modify.

## 2. Related architecture decisions

Check `docs/adr/` for any ADRs referenced by the spec (the spec will name
them, e.g. "ADR 024"). Read those ADRs for the reasoning behind the design —
don't deviate from a decision without flagging it first.

## 3. Existing code to reuse

Before writing new logic, look for existing implementations of the same
pattern elsewhere in the repo (e.g. how MCP tools do auth in
`mcp_server/tools.py`, or how `core/services.py` structures a service
function). Reuse and extend existing code rather than duplicating it.

## 4. Implementation rules

- Follow the spec's implementation checklist in order.
- Do not break existing functionality (existing tests must still pass).
- Do not add scope beyond what the spec describes — no speculative
  abstractions, no unrelated refactors.
- Write tests for what you build, matching the test structure in the spec.
- If the spec is ambiguous or conflicts with `docs/CLAUDE.md`, stop and ask
  rather than guessing.

## 5. Before you finish

- Run the test suite and confirm everything passes.
- Verify each item in the spec's "Success Criteria" section.
- Summarize what you built, what you deviated from (if anything) and why,
  and what's left undone.

Start by reading docs/CLAUDE.md, then the spec, then the prompt file, then
begin implementation.
```

---

## How to fill this in

| Placeholder | Replace with |
|---|---|
| `<SPEC_FILE>` | The spec's filename without `.md`, e.g. `SPEC_AGENT_REST_API` |
| `<PROMPT_FILE>` | The matching prompt filename, e.g. `PROMPT_AGENT_REST_API` |

If there's no dedicated prompt file for the task, delete step 2's second
paragraph and rely on the spec alone.

---

## Example (filled in)

```
Read docs/CLAUDE.md, then docs/spec/SPEC_AGENT_REST_API.md, then
docs/prompts/PROMPT_AGENT_REST_API.md. Implement the 5 REST endpoints,
following ADR 024 for the reasoning behind the tiered API design. Reuse
core/services.py and core/auth.py rather than duplicating logic. Write
tests per the spec's test section. Confirm all existing tests still pass
before reporting done.
```

---

## Notes

- This template assumes the coding agent has repo access and can run tests.
- Keep the actual spec and prompt files as the detailed source of truth —
  this template just points the agent to them and sets the ground rules.
- Update this template if `docs/CLAUDE.md` rules change or if the spec/prompt
  file structure changes.
