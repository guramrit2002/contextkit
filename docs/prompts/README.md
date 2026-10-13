# Coding Agent Prompts

Prompts handed to coding sessions to implement a spec from `docs/spec/`.

**Note:** This directory is gitignored — working documents, not shipped docs.

---

## Files

| File | Status | Purpose |
|---|---|---|
| `CODING_AGENT_TEMPLATE.md` | Active | Reusable prompt — fill in the spec/prompt names and hand to a coding session |
| `PROMPT_AGENT_REST_API.md` | ✅ Completed | Agent REST API task; kept as a reference example |
| `PROMPT_HORIZON_DEPLOY.md` | ✅ Completed | Make the MCP server deployable on Horizon + Supabase |
| `PROMPT_GET_KEY_FROM_WEBSITE.md` | ✅ Completed | Get-key dialog with GitHub sign-in + project-ID normalization |
| `PROMPT_WEB_RUNTIME_CONFIG.md` | 📋 Ready | Website reads backend URL and GitHub client ID from `/config.json` (spec Part 3) |
| `PROMPT_PROJECT_CLIENTS.md` | 📋 Ready (Part A urgent) | Ownership check, then many clients per project |

---

## Naming

- Specs: `docs/spec/SPEC_<FEATURE>.md`
- Prompts: `docs/prompts/PROMPT_<FEATURE>.md`

Use **client** for the API key identity and **agent** only for AI coding tools or the agent-facing API tier (ADR 025).

---

## Workflow

1. Design session writes the ADR (`docs/adr/`), then the spec, then (optionally) a task prompt.
2. Fill in `CODING_AGENT_TEMPLATE.md` and give it to a coding session.
3. Coding session implements, runs both test suites, reports back.
4. Design session updates the spec status and `docs/PROJECT_STATUS.md`.

## Related

- `docs/spec/` — specs
- `docs/adr/` — decisions
- `docs/PROJECT_STATUS.md` — current state
