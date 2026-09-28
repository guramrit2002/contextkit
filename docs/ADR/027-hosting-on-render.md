# ADR 027 — Host the MCP server on Render instead of Horizon

**Status:** Accepted

**Amends:** ADR 026 (hosting platform only)

## Context

ADR 026 chose Prefect Horizon to host the MCP server, with Horizon's own authentication turned off so that contextkit API keys are the only authentication.

On the first deploy, Horizon's authentication could not be turned off without upgrading to a paid plan. With it on, Horizon validates every `Authorization: Bearer` header as its own OAuth token before the request reaches contextkit:

- a request without a header gets HTTP 401 with an OAuth challenge;
- a request with a contextkit key (`ck_...`) gets HTTP 401 `invalid_token`.

So no contextkit key could ever reach the server, and Horizon's OAuth admits only members of the Horizon organization, which rules out public users (the reason ADR 026 turned it off).

Alternatives considered for a free host:

- **Koyeb:** no new deployments ("joining Mistral").
- **Railway, Fly.io:** trial credit only.
- **PythonAnywhere (free):** outbound network allow-list; cannot reach Supabase.
- **Cloudflare Workers:** Python cannot run psycopg.
- **Google Cloud Run:** fits well (scales to zero, fast cold starts, generous free tier) but needs a billing account.
- **Render (free web service):** no card, deploys from GitHub, sleeps when idle.

## Decision

Host the MCP server on a **Render free Web Service**. Everything else in ADR 026 stands: one Supabase Postgres database, `CONTEXTKIT_HOSTED=true`, contextkit API keys as the only authentication, migrations as a deploy step, and the startup schema check.

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `fastmcp run server.py:mcp --transport http --host 0.0.0.0 --port $PORT` |
| Environment | `DATABASE_URL`, `CONTEXTKIT_HOSTED=true`, `PYTHON_VERSION=3.12.14` |
| URL | `https://contextkit.onrender.com/mcp` |

Render assigns `PORT`; the server binds `0.0.0.0` so Render can route to it. There is no host-level authentication in front of the server, so the `Authorization` header reaches contextkit unchanged. This answers ADR 026's open question: verified on the live deploy, a missing key is rejected with "API key is required" and a wrong key with "Invalid API key", both audited in Supabase.

The unused `MCP_HOST` / `MCP_PORT` settings are removed. The host and port come from the start command, and Render sets the port.

## Consequences

- Free, with no card, and contextkit keys work directly.
- The free instance sleeps after about 15 minutes idle. The first request after that took about 20 seconds when measured (Render quotes up to about a minute). Agents may time out on the first connection and need one reconnect.
- One instance, and the free tier's monthly hours are limited. That is acceptable for early use.
- Moving to another host (Cloud Run, or a paid Render instance) needs only a new build and start configuration; the code is host-independent.

## Deferred

- A keep-alive ping to avoid cold starts; check Render's free-tier terms first.
- Moving to Cloud Run or a paid instance when cold starts or instance hours become a problem.
