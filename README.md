# contextkit

**Shared memory for your AI coding agents.**

Switch between Claude Code, Codex, Cursor and other agents without re-explaining your project. contextkit keeps your project's decisions, progress and session history, and hands all of it to whichever agent picks up next.

[Get started](#get-started) · [How it works](#how-it-works) · [Security](#security--privacy) · [Self-hosting](#self-hosting)

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

Keys look like `ck_...`. Each one works for exactly one project, identified by its git remote URL. Ask your contextkit admin for one, or create your own through the [user API](#api-keys).

### 2. Connect your agent

**Claude Code**

```bash
claude mcp add --transport http contextkit https://contextkit.onrender.com/mcp \
  --header "Authorization: Bearer ck_..."
```

<details>
<summary><b>Gemini CLI</b></summary>

```bash
gemini mcp add --transport http contextkit https://contextkit.onrender.com/mcp \
  --header "Authorization: Bearer ck_..."
```
</details>

<details>
<summary><b>VS Code (GitHub Copilot)</b></summary>

```bash
code --add-mcp '{"name":"contextkit","type":"http","url":"https://contextkit.onrender.com/mcp","headers":{"Authorization":"Bearer ck_..."}}'
```
</details>

<details>
<summary><b>Cursor</b></summary>

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "contextkit": {
      "url": "https://contextkit.onrender.com/mcp",
      "headers": { "Authorization": "Bearer ck_..." }
    }
  }
}
```
</details>

<details>
<summary><b>Windsurf</b></summary>

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "contextkit": {
      "serverUrl": "https://contextkit.onrender.com/mcp",
      "headers": { "Authorization": "Bearer ck_..." }
    }
  }
}
```
</details>

<details>
<summary><b>Codex</b></summary>

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.contextkit]
url = "https://contextkit.onrender.com/mcp"
http_headers = { "Authorization" = "Bearer ck_..." }
```
</details>

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
- **Open source:** every line is auditable.

Context is stored in the hosted Postgres database, not on your machine.

## Self-hosting

contextkit is two services sharing one Postgres database ([ADR 029](docs/ADR/029-deployed-database-only.md)):

- the **MCP server** that agents connect to, and
- a **Django backend** for the admin, API keys, and a REST API for tools without MCP.

**Database.** Create a Postgres database (Supabase works well) and use its session-pooler URL as `DATABASE_URL`, ending in `?sslmode=require`. Run the migrations from your machine before the first deploy and after every update:

```bash
alembic upgrade head
cd api && python manage.py migrate
```

**MCP server** ([ADR 027](docs/ADR/027-hosting-on-render.md)). On Render, create a Web Service from this repository:

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `fastmcp run server.py:mcp --transport http --host 0.0.0.0 --port $PORT` |
| Environment | `DATABASE_URL`, `CONTEXTKIT_HOSTED=true`, `PYTHON_VERSION=3.12.14` |

**Django backend** (Docker):

```bash
cp .env.example .env              # DATABASE_URL and DJANGO_SECRET_KEY (single-quoted)
docker compose build
docker compose run --rm migrate
docker compose up -d              # http://127.0.0.1:8002/admin/
docker compose run --rm api python manage.py createsuperuser
```

Behind your HTTPS proxy, set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `DJANGO_BEHIND_PROXY=true`.

### API keys

Admins create keys in the Django admin or with `python manage.py create_client --project-id <git remote> --name <name>`. Users can manage their own keys through the user API ([ADR 028](docs/ADR/028-user-api-keys.md)):

```bash
# Sign in (username and password, or POST a GitHub OAuth code to /api/v1/auth/github/)
curl -X POST https://<backend>/api/v1/auth/token/ -H "Content-Type: application/json" \
  -d '{"username": "you", "password": "..."}'

# Create a key for a project; it is shown only once
curl -X POST https://<backend>/api/v1/clients/ -H "Authorization: Bearer <access token>" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "https://github.com/you/repo.git", "name": "laptop"}'
```

`GET /api/v1/clients/` lists your keys, `POST /api/v1/clients/<id>/rotate/` replaces one, and `DELETE /api/v1/clients/<id>/` revokes it.

## Development

```bash
git clone https://github.com/guramrit2002/contextkit.git
cd contextkit
uv sync --extra backend --extra dev
cp .env.example .env        # set DATABASE_URL and DJANGO_SECRET_KEY

uv run pytest                                          # core and MCP server
cd api && uv run --extra backend python manage.py test # Django
```

The tests run on throwaway SQLite files and never touch `DATABASE_URL`. Architecture decisions live in [`docs/ADR/`](docs/ADR/).

## What's next

- Session compaction: fold old sessions into decisions and state automatically.
- A token budget for briefings on long-running projects.
- Sign-up and a dashboard for managing projects and keys.
- Rate limiting per key.

## Support

Found a bug or have an idea? [Open an issue](https://github.com/guramrit2002/contextkit/issues).
