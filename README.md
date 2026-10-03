<p align="center">
  <img src="web/public/favicon.svg" alt="contextkit logo" width="72" height="72">
</p>

<h1 align="center">contextkit</h1>

<p align="center"><b>Shared memory for your AI coding agents.</b></p>

Switch between Claude Code, Codex, Cursor and other agents without re-explaining your project. contextkit keeps your project's decisions, progress and session history, and hands all of it to whichever agent picks up next.

<p align="center">
  <a href="#get-started">Get started</a> · <a href="#how-it-works">How it works</a> · <a href="#security--privacy">Security</a>
</p>

---

## Why contextkit

Every time you switch AI coding tools, the new agent starts from zero. It re-asks questions, revisits settled decisions, and undoes conventions it never heard about. You end up writing handoff notes for a machine.

contextkit is an MCP server that every agent reads from and writes to. One agent records what it decided and where it stopped; the next one loads that briefing with a single call and keeps going.

- **Seamless handoffs:** move between Claude Code, Codex, Cursor, Gemini CLI, Windsurf or VS Code mid-task.
- **Decisions that stick:** every decision is stored with its reasoning and the alternatives that were rejected.
- **One key per agent:** give Claude Code, Codex and Cursor their own keys, revoke one without touching the others, and see which agent wrote what.
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

On [the contextkit website](https://contextkit-lime.vercel.app), click **Get key** and sign in with GitHub. Then:

1. **Pick the repository** from your public GitHub repositories.
2. **Pick the client:** the agent that will use the key (Claude Code, Codex, Cursor, Gemini CLI, VS Code (Copilot) or Windsurf), or **Add a new name…** for anything else, such as a CI job.
3. **Copy the key** (`ck_...`). It's shown once, together with the connect command for your agent.

Each key works for one project and is named `<project>-<client>-<key-id>`, e.g. `contextkit-claude-code-3f9a1c2b`. Use **Add agent** to give each tool its own key, and **Rotate** or **Revoke** a key from the same dialog.

> Keys are for **public repositories you own** on GitHub. Organisation, private and non-GitHub repositories aren't supported yet.

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

Every decision, session and audit entry records the key that wrote it, so with one key per agent you can see which agent did what.

## Security & privacy

- **Authenticated:** every call needs an API key; only its SHA-256 hash is stored.
- **Isolated:** each key can read and write exactly one project.
- **Owner only:** only a repository's owner on GitHub can create keys for it, and a project belongs to one account.
- **Redacted:** API keys, passwords and credentials are removed before anything is stored.
- **Audited:** every call, allowed or denied, is recorded.
- **Encrypted in transit:** HTTPS to the server, TLS to the database.

Context is stored in the hosted Postgres database, not on your machine.

## What's next

- Session compaction: fold old sessions into decisions and state automatically.
- A token budget for briefings on long-running projects.
- Organisation and private repositories, through a GitHub App.
- Sharing a project with a team.
- Rate limiting per key.
