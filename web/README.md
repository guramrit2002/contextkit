# contextkit website

Single-section landing page for contextkit (React + TypeScript, built with Vite), with an
optional **Get key** dialog: sign in with GitHub, enter a repository URL, copy a working API key
(ADR 030).

```bash
npm install
npm run dev      # http://localhost:5173
npm run lint
npm run build    # static files in dist/
```

## Get key dialog

The dialog needs two public settings: the Django backend that serves `/api/v1/`, and the GitHub
OAuth app's client ID. Without both, the **Get key** button is hidden and the site is fully
static: `dist/` can be served by any static host or CDN.

### Runtime config: `/config.json` (deployments)

The site reads both settings from `/config.json` on its own origin when the page loads, so a new
backend URL (for example after the Cloudflare quick tunnel restarts) needs only an edit to that
file, not a rebuild:

```json
{
  "apiBaseUrl": "https://<tunnel or domain>",
  "githubClientId": "<GitHub OAuth app client id>"
}
```

Copy `public/config.example.json` to `config.json` next to `index.html` in the deployed site.
`public/config.json` is gitignored: each deployment provides its own.

- **Public values only.** Everyone who visits the site can read this file. Never put the GitHub
  client secret, an API key or anything else secret in it.
- **Precedence per field:** a valid value in `config.json`, then the build-time variable below,
  then nothing.
- **Validation:** `apiBaseUrl` must be `https://` (`http://` only for `localhost` or `127.0.0.1`);
  `githubClientId` must match `^[A-Za-z0-9._-]{1,100}$`. Invalid values are ignored with a
  console warning.
- A missing file, bad JSON, a network error or a 3-second timeout never breaks the page; the
  build-time values apply.
- Serve it with `Cache-Control: no-store` (the site also fetches it with `cache: 'no-store'`), so
  a changed URL applies on the next page load.

### Build-time fallback (local development)

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | The Django backend that serves `/api/v1/`, no trailing slash |
| `VITE_GITHUB_CLIENT_ID` | Client ID of the GitHub OAuth app |

Set them in `web/.env.local` (see `.env.example`). `config.json` overrides them.

When they are set:

- the GitHub OAuth app's callback URL must be this site's origin plus `/`;
- the backend needs `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` from the same app, and this
  site's origin in `DJANGO_CORS_ALLOWED_ORIGINS`.

The access token and any issued key live only in the page's memory and are dropped when the
dialog closes. `sessionStorage` holds only the OAuth state, a reopen flag and the selected agent,
and only until GitHub sends the user back.

## Local development without GitHub

The backend can stand in for GitHub (sign-in, your repository list and the ownership check), so
the Get key flow works locally without an OAuth app or network. It only runs with
`DJANGO_DEBUG=true` on a **local SQLite database**: it approves repository ownership, so it
refuses to start against the shared Postgres database (system check `accounts.E001`).

Backend (from `api/`):

```bash
export DATABASE_URL="" CONTEXTKIT_ALLOW_SQLITE=true CONTEXTKIT_HOSTED=true
export CONTEXTKIT_DB_PATH=~/.contextkit-local/core.sqlite3 DJANGO_DB_PATH=~/.contextkit-local/django.sqlite3
export DJANGO_DEBUG=true DJANGO_SECRET_KEY=local-dev-only DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:5180
export GITHUB_MOCK=true GITHUB_MOCK_LOGIN=you GITHUB_MOCK_REPOS=app,tool   # optional: login and repos
(cd .. && alembic upgrade head) && python manage.py migrate
python manage.py runserver 127.0.0.1:8010
```

`DATABASE_URL` must be exported **empty**, not unset, or `.env` fills in the shared database.

Website (`web/.env.local`):

```bash
VITE_API_BASE_URL=http://127.0.0.1:8010
VITE_GITHUB_CLIENT_ID=local-mock
VITE_GITHUB_AUTHORIZE_URL=http://127.0.0.1:8010/api/v1/auth/github/mock-authorize/
```

Then `npm run dev -- --port 5180 --strictPort` and open `http://localhost:5180/`. **Continue with
GitHub** returns at once, signed in as the mock login, and the picker lists the mock repositories.

