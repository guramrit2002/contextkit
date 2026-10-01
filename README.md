# contextkit

**Shared memory for your AI coding agents.**

Switch between Claude Code, Codex, Cursor and other agents without re-explaining your project. contextkit keeps your project's decisions, progress and session history, and hands all of it to whichever agent picks up next.

[Get started](#get-started) · [How it works](#how-it-works) · [Security](#security--privacy)

---

## Why contextkit

Every time you switch AI coding tools, the new agent starts from zero. It re-asks questions, revisits settled decisions, and undoes conventions it never heard about. You end up writing handoff notes for a machine.

contextkit is an MCP server that every agent reads from and writes to. One agent records what it decided and where it stopped; the next one loads that briefing with a single call and keeps going.

- **Seamless handoffs:** move between Claude Code, Codex, Cursor, Gemini CLI, Windsurf or VS Code mid-task.
- **Decisions that stick:** every decision is stored with its reasoning and the alternatives that were rejected.
- **Nothing to install:** connect a hosted server with one command and an API key.
- **Secure by default:** every call is authenticated, limited to one project, redacted and audited.

## How it works

1. **Start a task.** Your agent calls `get_context` and receives the project briefing: decisions so far, current state, and recent sessions.
2. **Work.** As it goes, the agent records decisions with `log_decision` and progress with `update_state`.
3. **Hand off.** Before finishing, the agent writes a session summary with `log_session`.
4. **Switch agents.** The next agent, in any tool, calls `get_context` and continues where the last one stopped.

The server tells agents to do this on its own, so there are no rules to add to your repository.

| Tool | What it does |
|---|---|
| `get_context` | Loads the project briefing at the start of a task |
| `log_decision` | Records a decision, its reasoning, and the alternatives considered |
| `update_state` | Replaces the current progress, next steps and blockers |
| `log_session` | Appends a summary of the work done in this session |
| `export_markdown` | Returns the project's full context as readable markdown |

## Get started

### 1. Get an API key

Keys look like `ck_...`. Each one works for exactly one project, identified by its git remote URL. Ask your contextkit admin for one.

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

### 3. Start working

Open your project and give your agent a task. It loads the briefing first and logs its work before it finishes.

> The hosted server sleeps when idle, so the first request after a quiet period can take up to a minute. If your agent times out on the first connection, reconnect once.

## What contextkit remembers

| | Contains | How it changes |
|---|---|---|
| **Decisions** | What was decided, why, and the alternatives considered | Appended; never overwritten |
| **Current state** | Progress, next steps, blockers | Replaced on each update |
| **Sessions** | A summary of each agent's work, and which key wrote it | Appended at the end of every session |

## Security & privacy

- **Authenticated:** every call needs an API key; only its SHA-256 hash is stored.
- **Isolated:** each key can read and write exactly one project.
- **Redacted:** API keys, passwords and credentials are removed before anything is stored.
- **Audited:** every call, allowed or denied, is recorded.
- **Encrypted in transit:** HTTPS to the server, TLS to the database.

Context is stored in the hosted Postgres database, not on your machine.

## What's next

- Session compaction: fold old sessions into decisions and state automatically.
- A token budget for briefings on long-running projects.
- Sign-up and a dashboard for managing projects and keys.
- Rate limiting per key.
