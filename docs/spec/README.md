# Implementation Specifications

Technical specs: what to build and how. Coding sessions read these; design sessions write them.

**Note:** This directory is gitignored — working documents, not shipped docs.

---

## Specs

| Spec | Status | What |
|---|---|---|
| `SPEC_CLIENT_AUTH.md` | ✅ Completed | Client API keys, one-project authorization, audit log (ADR 020, 022, 023, 025) |
| `SPEC_AGENT_REST_API.md` | ✅ Completed | The 5 MCP tools over HTTP at `/api/agent/v1/context/` (ADR 024) |
| `SPEC_HORIZON_DEPLOY.md` | ✅ Completed | Deploy the MCP server on Horizon with Supabase Postgres (ADR 026) |
| `SPEC_GET_KEY_FROM_WEBSITE.md` | Parts 1–2 ✅, Part 3 📋 | GitHub sign-in "Get key" dialog on the website, plus project-ID normalization (ADR 030); Part 3: runtime `/config.json` |
| `SPEC_PROJECT_CLIENTS.md` | 📋 Ready (Part A urgent) | Project ownership check, and many clients (one per agent) per project (ADR 031) |

Next up (not written yet): platform internal APIs (`/api/internal/`), per-user keys.

---

## Terminology

- **Client** — anything holding an API key (AI agent over MCP, or script/webhook/CI over REST). Used for the table, model, `client_id` columns and `core.auth` functions.
- **Agent** — an AI coding tool (Claude Code, Codex, Cursor). Also names the agent-facing API tier (`/api/agent/v1/`).

See ADR 025.

---

## How to use

1. Read the spec.
2. Read the matching prompt in `docs/prompts/`, if there is one.
3. Follow the checklist and verify the success criteria.

## Related

- `docs/adr/` — why decisions were made
- `docs/prompts/` — prompts for coding sessions
- `docs/PROJECT_STATUS.md` — current state
