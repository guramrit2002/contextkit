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

### Local mode

Run contextkit on your machine with SQLite. No network calls, no API key needed (unless you set `REQUIRE_AUTH=true`).

**Requirements:** Python 3.12+, uv

```bash
git clone https://github.com/anthropics/contextkit.git
cd contextkit
uv sync
python3 -m uv run python -m mcp_server
```

Then register the server with your agent:

**Claude Code:**
```bash
claude mcp add contextkit -- python3 -m uv run python -m mcp_server
```

**Codex:** Add to `~/.codex/config.toml`:
```toml
[mcp_servers.contextkit]
command = "python3"
args = ["-m", "uv", "run", "python", "-m", "mcp_server"]
```

**Cursor, Windsurf, Gemini CLI:** See [docs/guide/](docs/guide/) for setup instructions.

Context is stored in `~/.contextkit/contextkit.db` (SQLite), which you can back up or version-control manually.

### Hosted mode (coming soon)

Store context on a shared server so all your agents have the same briefing, whether you're on the same machine or not. Requires an API key (free tier available).

1. Visit [contextkit-lime.vercel.app](https://contextkit-lime.vercel.app) and sign in with GitHub.
2. Create an API key for a public repository you own.
3. Register the key with your agent (setup varies by tool).

Each API key works for one project. Create multiple keys—one per agent—to see which tool wrote what in the audit log.

---

## What contextkit stores

| | Contains | How it changes |
|---|---|---|
| **Decisions** | What was decided, why, alternatives considered | Appended; never overwritten |
| **Current state** | Progress this week, next steps, blockers | Replaced on each update |
| **Sessions** | A summary of each agent's work, and which key/agent wrote it | Appended after every session |

## Security & privacy

### Local mode
- **No network:** context stays on your machine in `~/.contextkit/contextkit.db`.
- **No authentication:** unless `REQUIRE_AUTH=true` is set, calls don't need an API key.
- **No redaction:** secrets are your responsibility. Provide clean code and prompts.

### Hosted mode (future)
- **Authenticated:** every call requires an API key; only the SHA-256 hash is stored.
- **Isolated:** each key can read and write exactly one project.
- **Project ownership:** only a repository's owner on GitHub can create keys for it.
- **Redacted:** API keys, passwords, and common credentials are removed from all text before storage or summarization.
- **Audited:** every call—allowed or denied—is recorded with client, tool, status, and timestamp.
- **Encrypted in transit:** HTTPS to the server, TLS to the database (Supabase Postgres).
- **No telemetry:** your context is never used to train models or improve the service.

Context is stored in a PostgreSQL database, not on your machine. Encryption at rest is not yet available; do not store unencrypted secrets in decisions or session summaries.

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
| Shared infrastructure (hosted mode) | — Not applicable | ✓ Multiple machines |

**Keep CLAUDE.md if:** You're the only person working on a small project, use one agent, and rarely clear your session.

**Use contextkit alongside CLAUDE.md:** Some teams keep CLAUDE.md for human-readable onboarding and use contextkit for agent-to-agent handoffs.

---

## When you don't need contextkit

- **Solo + single tool + no compaction:** If you're the only developer, use only Claude Code, and never hit the session limit, a CLAUDE.md file is simpler and faster.
- **Ad-hoc tasks:** One-off scripts or small fixes where context loss doesn't matter.
- **Lightweight observability:** If you only need to know what the agent *did*, not *why*, an audit log is cheaper than storing decisions.

---

## Shipped (v0.2+)

✓ 5 MCP tools (get_context, log_decision, update_state, log_session, export_markdown)  
✓ Local mode with SQLite  
✓ Hosted mode with API key authentication  
✓ REST API for agents without MCP (`/api/agent/v1/`)  
✓ Secret redaction (regex-based; see `core/redaction.py`)  
✓ Audit logging (every call, auth or deny)  
✓ Django admin for key management (hosted mode)  
✓ 5 agent setup guides (Claude Code, Codex, Cursor, Gemini CLI, VS Code, Windsurf)  

## Next

- Session compaction: fold old sessions into decisions and state automatically.
- Session-start and pre-compaction hooks: call code to keep context fresh.
- Smarter context retrieval: include only the decisions and sessions relevant to the current task, within a token budget.
- Usage stats per API key.

## Later

- Decision ↔ file linking: link decisions to the code they affect.
- Staleness detection: flag decisions that may no longer be valid.
- Conflict detection: warn when two agents made incompatible decisions.
- Team sharing with RBAC.
- Organisation and private repositories via GitHub App.
- Bring-your-own database (any Postgres instance).
- ADR and PR exports.

---

## Architecture

- **MCP server:** FastMCP, thin transport layer only.
- **Core:** Plain Python with Pydantic schemas and SQLAlchemy ORM.
- **Database:** SQLite locally; PostgreSQL (Supabase) in hosted mode.
- **Django:** API, key management, audit viewing (hosted mode only).
- **Tests:** 160+ pytest, 48+ Django, 95%+ coverage.

See [docs/](docs/) for architecture decisions (ADRs), setup guides, and the full project status.

## Contributing

This project is in early development. Ideas, feedback, and contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) (coming soon).

## License

TBD
