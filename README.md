<p align="center">
  <img src="web/public/favicon.svg" alt="contextkit logo" width="72" height="72">
</p>

<h1 align="center">contextkit</h1>

<p align="center"><b>Project memory for AI coding agents.</b></p>

<p align="center">Decisions, progress, and reasoning that survive new sessions, tool switches, and cleared context.</p>

<p align="center">
  <a href="#get-started">Get started</a> · <a href="#how-it-works">How it works</a> · <a href="#shipped">Features</a> · <a href="#why-not-claudemd">Why not CLAUDE.md?</a> · <a href="#security--privacy">Security</a>
</p>

---

## The problem

Every time your AI agent's context window clears—after `/clear`, during session compaction, or when you switch tools—it forgets why your code is shaped the way it is. It re-asks settled questions, reverses old decisions, and breaks conventions it never learned about. You end up writing handoff notes for a machine.

Even solo developers who never switch tools face this. A week later, your agent doesn't remember the trade-off you made, the library you rejected, or the refactor you were in the middle of.

## The solution

contextkit is an MCP server that every agent reads from and writes to. One agent records what it decided, why, and where it stopped; the next one—whether it's the same tool or a different one—loads that briefing with a single call and keeps going.

- **Decisions stick:** every decision is stored with its reasoning and the alternatives that were rejected, not just the final outcome.
- **Progress persists:** session history and current state survive context clears, tool switches, and compaction.
- **Reasoning travels:** when you switch tools or clear the session, the reasoning behind old decisions goes with you.
- **Secure:** API keys are hashed, calls are audited, secrets are redacted before storage.

## How it works

1. **Start a task.** Your agent calls `get_context` and receives the project briefing: key decisions, current state, and recent work.
2. **Work.** As it goes, the agent records decisions with `log_decision` and progress with `update_state`.
3. **Hand off.** Before finishing, it writes a session summary with `log_session`.
4. **Switch tools or clear.** The next agent calls `get_context` and continues where the last one stopped.

Agents are instructed to do this when you add contextkit to your project. Hooks are coming to make it automatic.

| Tool | What it does |
|---|---|
| `get_context` | Load the project briefing: decisions, current state, recent sessions |
| `log_decision` | Record a decision, why it was made, and alternatives considered |
| `update_state` | Replace the current progress, next steps, and blockers |
| `log_session` | Append a summary of the work done this session |
| `export_markdown` | Export the full context as readable markdown |

---

## Get started

### 1. Get an API key

On [the contextkit website](https://contextkit-lime.vercel.app), sign in with GitHub to create an API key for a public repository you own. You'll get a setup command for your agent.

Each key works for one project. Create multiple keys—one per agent—to see which tool wrote what.

### 2. Connect your agent

Pick your agent and follow its guide:

| Agent | Setup guide |
|---|---|
| Claude Code | [docs/guide/claude-code.md](docs/guide/claude-code.md) |
| Codex | [docs/guide/codex.md](docs/guide/codex.md) |
| Cursor | [docs/guide/cursor.md](docs/guide/cursor.md) |
| Gemini CLI | [docs/guide/gemini-cli.md](docs/guide/gemini-cli.md) |
| VS Code (GitHub Copilot) | [docs/guide/vscode.md](docs/guide/vscode.md) |
| Windsurf | [docs/guide/windsurf.md](docs/guide/windsurf.md) |

---

## What contextkit stores

| | Contains | How it changes |
|---|---|---|
| **Decisions** | What was decided, why, alternatives considered | Appended; never overwritten |
| **Current state** | Progress this week, next steps, blockers | Replaced on each update |
| **Sessions** | A summary of each agent's work, and which key/agent wrote it | Appended after every session |

## Security & privacy

- **Authenticated:** every call requires an API key (SHA-256 hash stored).
- **Isolated:** each key can read and write exactly one project.
- **Project ownership:** only a repository's owner on GitHub can create keys for it.
- **Redacted:** API keys, passwords, and common credentials are removed from all text before storage or summarization.
- **Audited:** every call—allowed or denied—is recorded with client, tool, status, and timestamp.
- **Encrypted in transit:** HTTPS to the server, TLS to the database.
- **No telemetry:** your context is never used to train models or improve the service.

Context is stored in a PostgreSQL database (Supabase recommended). Encryption at rest is not yet available; do not store unencrypted secrets in decisions or session summaries.

---

## Why not CLAUDE.md?

A `CLAUDE.md` file works great for small solo projects or one-off tasks. contextkit wins when:

| Scenario | CLAUDE.md | contextkit |
|----------|-----------|-----------|
| One developer, one tool, rarely clears context | ✓ Simpler | — Not needed |
| Multiple agents or tool switches | — Manual sync | ✓ Automatic |
| Sessions get compacted or cleared | — Lost reasoning | ✓ Preserved |
| Teammates need the same briefing | — Copy the file | ✓ One source |
| You need a record of past work | — Single snapshot | ✓ History |
| Decisions with reasoning | — Free text | ✓ Structured |
| Shared across machines | — Not applicable | ✓ Postgres backend |

**Keep CLAUDE.md if:** You're the only person working on a small project, use one agent, and rarely clear your session.

**Use contextkit alongside CLAUDE.md:** Some teams keep CLAUDE.md for human-readable onboarding and use contextkit for agent-to-agent handoffs.

---

## When you don't need contextkit

- **Solo + single tool + no compaction:** If you're the only developer, use only Claude Code, and never hit the session limit, a CLAUDE.md file is simpler and faster.
- **Ad-hoc tasks:** One-off scripts or small fixes where context loss doesn't matter.
- **No PostgreSQL available:** If you don't have access to a Postgres database, contextkit isn't usable yet.

---

## Shipped (v0.2+)

✓ 5 MCP tools (get_context, log_decision, update_state, log_session, export_markdown)  
✓ PostgreSQL support (required; ADR 029)  
✓ API key authentication and audit logging  
✓ REST API for agents without MCP (`/api/agent/v1/`)  
✓ Secret redaction (regex-based; see `core/redaction.py`)  
✓ 5+ agent setup guides (Claude Code, Codex, Cursor, Gemini CLI, VS Code, Windsurf)  

---

## Architecture

- **MCP server:** FastMCP, thin transport layer only.
- **Core:** Plain Python with Pydantic schemas and SQLAlchemy ORM.
- **Database:** PostgreSQL (required; ADR 029).
- **Django:** API, key management, audit viewing.
- **Tests:** 160+ pytest, 48+ Django, 95%+ coverage (tests use SQLite, production requires Postgres).

See [docs/](docs/) for architecture decisions (ADRs), setup guides, and the full project status.
