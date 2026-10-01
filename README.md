# contextkit

**AI-Powered Project Context Management**

> Seamlessly hand off work between AI coding agents without losing context, decisions, or progress.

---

## Why contextkit?

When you use multiple AI tools (Claude Code, Codex, Cursor) on the same project, switching between them means losing context. Each agent re-asks questions, revisits decisions, or breaks established conventions because it doesn't know what the last one did.

**contextkit solves this.** It's a unified context platform that every AI agent can read and write to, creating a continuous, shared understanding of your project. When you switch tools, the next agent picks up exactly where the last one left off—automatically.

### Features

✨ **Automatic Context Management** — Agents load full project briefings on startup, including architecture, decisions, progress, and blockers  
🔄 **Seamless Handoffs** — Switch between Claude Code, Codex, and Cursor with zero context loss  
🛡️ **Secure by Default** — An API key on every call, one project per key, secrets redacted before storage, every call audited  
📊 **Persistent History** — Every decision and work session is recorded and searchable  
🔌 **Tool-Agnostic** — Works with any MCP-compatible AI coding agent  
⚡ **Zero Setup** — Install once, use everywhere—all agents automatically access the same context

## How It Works

### The Workflow

1. **Agent Starts** — Claude Code (or any MCP-compatible agent) connects to contextkit and calls `get_context`
2. **Context Loaded** — The agent receives a complete briefing: architecture, decisions made, current progress, known blockers, and recent work
3. **Agent Works** — As the agent makes progress, it automatically logs decisions (`log_decision`) and updates state (`update_state`)
4. **Session Ends** — Before finishing, the agent logs a session summary (`log_session`)
5. **Switch Tools** — Open Codex or Cursor on the same project
6. **Zero Context Loss** — The new agent loads the exact same context the previous agent had, plus everything that happened since

### What contextkit Remembers

| Layer | Contains | Updates |
|-------|----------|---------|
| **Stable Context** | Stack, architecture, conventions, rules | Rarely changed |
| **Decisions** | What was decided, why, alternatives considered | Continuously appended |
| **Current State** | Progress, next steps, blockers | Real-time updates |
| **Work Sessions** | Summary of each agent's work | Automatically logged |

### Security First

- **Automatic Redaction** — API keys, credentials, and sensitive data are redacted before storage
- **API Keys** — Every call is authenticated, limited to its key's project, and audited
- **Open Source** — Fully auditable, no vendor lock-in

## Architecture

```mermaid
flowchart TD
    A[AI agents<br/>Claude Code, Codex, Cursor] --> M[MCP server<br/>FastMCP]
    N[Non-MCP clients<br/>step 3]:::later --> R[REST API<br/>step 3]:::later
    M --> C[Core services<br/>plain Python]
    R --> C
    C --> D[(Postgres<br/>Supabase)]
    D -.reads.-> J[Django<br/>onboarding, dashboards, step 2]:::later
    U[Users in browser]:::later --> J
    classDef later stroke-dasharray: 5 5
```

- **MCP server:** a thin transport layer. It defines tools and calls core; it contains no business logic.
- **Core services:** a plain Python package with no Django dependency. It handles briefing assembly, compaction, redaction, and storage.
- **Database:** one Postgres database (Supabase), shared by core and Django ([ADR 029](docs/ADR/029-deployed-database-only.md)).
- **Django (step 2):** onboarding, API keys, and analytics. It reads context tables but never writes them.

Only core writes to the context tables. See [`docs/adr/`](docs/adr/) for the full list of architecture decisions.

## MCP tools

| Tool | Purpose |
|---|---|
| `get_context` | Return the project briefing for the agent to load |
| `log_decision` | Record a decision and its reasoning |
| `update_state` | Replace the current state: progress, next steps, blockers |
| `log_session` | Append a summary of the work session |
| `export_markdown` | Export the project context as a readable markdown file |

## Repository structure

```
contextkit/
├── core/            # plain Python: schemas, services, storage
│   ├── schemas.py
│   ├── services.py
│   ├── briefing.py
│   ├── compaction.py
│   ├── redaction.py
│   └── storage.py
├── mcp_server/      # FastMCP server, imports core
├── backend/         # Django (step 2): onboarding and analytics
├── docs/
│   └── adr/         # architecture decision records
└── tests/
```

## Hosted (no install)

Get an API key (`ck_...`) for your project, then add the hosted server to your agent. Nothing to clone or install. Every call is authenticated with your key, limited to that key's project, and audited.

#### Claude Code

```bash
claude mcp add --transport http contextkit https://contextkit.onrender.com/mcp \
  --header "Authorization: Bearer ck_..."
```

#### Cursor

Add to `~/.cursor/mcp.json` (or `.cursor/mcp.json` in the project):

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

#### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.contextkit]
url = "https://contextkit.onrender.com/mcp"
http_headers = { "Authorization" = "Bearer ck_..." }
```

Over HTTP, `export_markdown` returns the markdown instead of writing a file.

The hosted server runs on a free instance that sleeps when idle, so the first request after a quiet period can take 20–60 seconds. If your agent times out on the first connection, reconnect once.

### Deploying your own hosted server

The hosted server is a plain Python web service backed by Postgres ([ADR 027](docs/ADR/027-hosting-on-render.md)). On [Render](https://render.com), create a **Web Service** from this repository:

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `fastmcp run server.py:mcp --transport http --host 0.0.0.0 --port $PORT` |
| Instance type | Free |
| Environment | `DATABASE_URL` (Supabase session pooler, `?sslmode=require`), `CONTEXTKIT_HOSTED=true`, `PYTHON_VERSION=3.12.14` |

Render sets `PORT` itself. Before the first deploy, and after any schema change, run the migrations from your machine with the same `DATABASE_URL`:

```bash
alembic upgrade head
cd api && python manage.py migrate
```

The server refuses to start if the database is behind. Create API keys with `python manage.py create_client --project-id <git remote> --name <name>` (also with `DATABASE_URL` set).

## Backend in Docker

The Django backend (admin, API key issuing, and the agent REST API at `/api/agent/v1/`) ships as a Docker image. The MCP server is deployed separately (see above). Both use the database in `DATABASE_URL`.

```bash
cp .env.example .env              # set DATABASE_URL and DJANGO_SECRET_KEY (single-quoted)
docker compose build
docker compose run --rm migrate   # core (Alembic) then Django migrations; run on every deploy
docker compose up -d              # http://127.0.0.1:8002/admin/
docker compose run --rm api python manage.py createsuperuser
docker compose run --rm api python manage.py create_client --project-id <git remote> --name <name>
```

The container listens on port 8000 and publishes it only on `127.0.0.1:8002`. Put a reverse proxy in front for HTTPS, and set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `DJANGO_BEHIND_PROXY=true` for your domain.

### User API: get your own API key

The website's **Get your API key** button signs you in with GitHub and issues a key. Scripts and admin-created accounts can use the API directly ([ADR 028](docs/ADR/028-user-api-keys.md)):

```bash
# Log in: returns a JWT access token (15 min) and refresh token
curl -X POST https://<backend>/api/v1/auth/token/ -H "Content-Type: application/json" \
  -d '{"username": "you", "password": "..."}'

# Create a key for a project (shown once)
curl -X POST https://<backend>/api/v1/clients/ -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "https://github.com/you/repo.git", "name": "laptop"}'
```

`GET /api/v1/clients/` lists your keys, `POST /api/v1/clients/<id>/rotate/` replaces one, and `DELETE /api/v1/clients/<id>/` revokes it.

## Development

contextkit runs only against the deployed Postgres database; there is no local-database mode ([ADR 029](docs/ADR/029-deployed-database-only.md)).

```bash
git clone https://github.com/guramrit2002/contextkit.git
cd contextkit
uv sync --extra backend --extra dev
cp .env.example .env        # set DATABASE_URL (Supabase session pooler) and DJANGO_SECRET_KEY
```

Without `DATABASE_URL` the MCP server and Django refuse to start with a clear error. The test suites never touch it: they run on throwaway SQLite files.

```bash
uv run pytest                                          # core and MCP server
cd api && uv run --extra backend python manage.py test # Django
```

## Usage

### For AI Agents

Agents automatically use contextkit when configured. Add this to your project's `CLAUDE.md`:

```markdown
## Shared Context with contextkit

The project uses contextkit to maintain shared context across AI agents.

**At the start:** Call `get_context` to load the project briefing  
**When deciding:** Call `log_decision` with your reasoning  
**Before finishing:** Call `update_state` and `log_session`

This enables seamless handoffs between Claude Code, Codex, Cursor, and other agents.
```

### For Humans

Ask your agent to call `export_markdown` to get the project's full context as markdown.

## Privacy & Security

Your project context is sensitive. contextkit treats it that way:

- ✅ **Authenticated** — Every call needs an API key; only its SHA-256 hash is stored
- ✅ **Isolated** — Each key can read and write exactly one project
- ✅ **Automatic Redaction** — API keys, passwords and credentials are redacted before storage
- ✅ **Audited** — Every call, allowed or denied, is recorded
- ✅ **Encrypted in transit** — HTTPS to the server, TLS to the database
- ✅ **Open Source** — Fully auditable code

Context is stored in the hosted Postgres database, not on your machine.

## Roadmap

**Current (v1.0)** — Hosted MCP server, Postgres storage, 5 core tools, per-project API keys

**v1.1** — Multi-agent support, session compaction, token budget management  
**v2.0** — Django backend, browser dashboard, PostgreSQL support  
**v2.1** — Team collaboration, API keys, usage analytics

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

- 📖 **Documentation** — See [docs/](docs/) for detailed guides
- 🐛 **Issues** — Found a bug? [Open an issue](https://github.com/guramrit2002/contextkit/issues)
- 💬 **Discussions** — Questions? [Start a discussion](https://github.com/guramrit2002/contextkit/discussions)

## License

MIT License — See [LICENSE](LICENSE) for details.
