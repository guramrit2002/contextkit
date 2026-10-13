# Implementation Spec: Get an API key from the website

**Created:** 2026-10-02
**Status:** Parts 1–2 done (merged into `dev`); Part 3 done on `feature/web-runtime-config`
**Context:** ADR 030 (read it first), ADR 012, 022, 025, 028, 029

---

## Overview

A user clicks **Get key** on the website, signs in with GitHub, lands back in the same dialog, enters a repository URL and copies a working `ck_…` key. Returning users see their keys and can rotate, revoke or add one.

The work has two parts:

1. **Project-ID normalization (backend, do first).** Any form of a repository URL must map to one canonical project ID, so the URL a user types matches what their agent sends.
2. **The key dialog (website).** Restore the dialog removed in `8245771` and replace its password sign-in with GitHub.

The backend endpoints already exist and stay as they are:
- `POST /api/v1/auth/github/`
- `GET` and `POST /api/v1/clients/`
- `POST /api/v1/clients/{id}/rotate/`
- `DELETE /api/v1/clients/{id}/`

**Decisions already made (don't revisit):**
- Full-page redirect to GitHub, not a popup.
- The repository is picked from the user's public GitHub repositories, with a typed URL as a fallback (changed 2026-10-03, option A: no new OAuth scope; private repos later via a GitHub App).
- A returning user sees their key list with Rotate, Revoke and New key.
- One key per project (ADR 022).

---

## Part 1 — Project-ID normalization

### 1.1 `core/projects.py` (new, plain Python)

`normalize_project_id(raw: str) -> str`

| Input | Output |
|---|---|
| `https://github.com/Owner/Repo.git` | `https://github.com/owner/repo` |
| `http://github.com/owner/repo/` | `https://github.com/owner/repo` |
| `https://user:token@github.com/owner/repo` | `https://github.com/owner/repo` |
| `git@github.com:owner/repo.git` | `https://github.com/owner/repo` |
| `ssh://git@github.com:22/owner/repo.git` | `https://github.com/owner/repo` |
| `git://github.com/owner/repo` | `https://github.com/owner/repo` |
| `github.com/owner/repo` | `https://github.com/owner/repo` |
| `https://GitLab.com/Group/Sub/Repo.git` | `https://gitlab.com/Group/Sub/Repo` (host lowercased, path kept) |
| `  /Users/me/app/  ` | `/Users/me/app` (not a remote: trim only) |

Rules:
- **Accepted schemes:** `https`, `http`, `ssh`, `git`, the scp-style `user@host:path`, and a bare `host/path` where the host contains a dot.
- **Removed:** credentials, port, a trailing `.git`, trailing `/`, surrounding whitespace.
- **Case:** the host is lowercased. For `github.com`, the whole path is lowercased too.
- **Idempotent:** `normalize(normalize(x)) == normalize(x)`.
- **Empty or whitespace input** raises `ValueError`, the same as `core.redaction.validate_project_id` does today, so existing callers and tests that expect `ValueError` keep working.
- **Length:** the result must still be at most 500 characters, as `core.redaction.validate_project_id` already enforces.

### 1.2 Apply it everywhere a project ID enters

- `core/redaction.py:validate_project_id`: return the normalized value. This covers every tool input that goes through `core/validation.py`.
- `core/storage.py:detect_project_id` (local mode): normalize the detected remote.
- `core/auth.py:validate_client_project_access`: compare `normalize(requested)` with `normalize(client.project_id)`, and return the client's stored project.
- `core/storage.py:get_or_create_project`:
  - the hosted branch's `URL_PREFIXES` check still works on canonical IDs, since they start with `https://`;
  - the local branch stores the `git config` remote as `git_remote`: normalize it too, so new projects never record a raw `git@…:….git` remote.
- `core/auth.py:guarded_call`: a denied call writes the requested project ID to `audit_log`. Write its normalized form; if normalization raises, write it as given.
- `api/clients/services.py:create_client`: store `normalize_project_id(project_id)`. Django importing `core` is allowed; core still imports no framework.
- `api/clients/serializers.py:CreateClientRequest.project_id`: update `help_text` to "Repository URL (any form: https, SSH, with or without .git)".
- **Duplicate project:** when the user already has a client for the normalized project, `POST /api/v1/clients/` returns 400 with "You already have a key for this repository. Rotate it instead." This replaces the default unique-constraint message.

### 1.3 Migrate existing data

**Alembic `core/migrations/versions/0004_normalize_project_ids.py`:**
- Copy the normalization function into the migration file (frozen; don't import `core.projects`).
- For each `projects.id` whose normalized form differs:
  - **If the canonical ID doesn't exist:** insert a project row with the canonical ID, copying `local_path`, `user_id` and the timestamps. Set `git_remote` to the canonical ID when the old remote was a URL, and recompute `name` as the last path segment of the canonical ID (what `get_or_create_project` does for new projects), so `contextkit.git` becomes `contextkit`. Repoint `decisions`, `sessions` and `state` to it, then delete the old row.
  - **If it already exists (merge):** repoint `decisions` and `sessions`. For `state`, which allows one row per project, keep the row with the newest `updated_at` and delete the other. Then delete the old project row.
- Rewrite `audit_log.project_id` to the canonical form.
- Run everything in one transaction and log what was renamed and merged.
- `downgrade()`: no-op with a comment. Merges can't be undone.

**Django `api/clients/migrations/0002_normalize_project_ids.py`** (RunPython, frozen copy of the function):
- Normalize every `Client.project_id`.
- If two clients of the same `user_id` collapse to one project, **raise** with their ids and names. Don't delete either; the operator decides which key to revoke.
- Reverse: no-op.

### 1.4 Tests

- `tests/test_projects.py`:
  - every row of the table in 1.1;
  - idempotence;
  - empty input raises `ValueError`;
  - over-length output raises.
- `tests/test_storage.py` (or the existing local-mode project test): a project created in local mode from a `git@…:….git` remote stores the canonical `git_remote`.
- `tests/test_auth.py`: a denied call's `audit_log` row holds the normalized project ID.
- `tests/test_auth.py`: a client stored as `https://github.com/o/r` is authorized for `git@github.com:o/r.git` and `https://github.com/O/R/`, and refused for `https://github.com/o/other`.
- `tests/test_services.py`: a tool call with a non-canonical `project_id` writes rows under the canonical ID.
- `tests/test_migrations.py`, following the existing migration tests:
  - 0004 renames a `.git` project, recomputes its name and moves its decisions, sessions and state;
  - it merges two variants of one project, keeping the newest state;
  - it rewrites `audit_log`.
- `api/clients/test_api.py`:
  - create stores the canonical ID and returns it in the response;
  - a second create for another form of the same repo returns 400 with the message above.
- Django migration 0002: normalizes, and raises on a same-user collision.

---

## Part 2 — The key dialog (`web/`)

### 2.1 Restore the removed dialog

Bring back these files from `git show 8245771^:<path>` as the starting point:
- `web/src/ApiKeyModal.tsx`
- `web/src/api.ts`
- `web/src/vite-env.d.ts`
- `web/.env.example`
- the dialog styles in `web/src/index.css`

The old dialog already has the patterns to keep:
- a native `<dialog>` with focus handling, Esc and backdrop;
- the JWT and key held in memory only and reset on close;
- `ApiError` with clear messages for 429, validation errors and an unreachable backend;
- the copy buttons.

### 2.2 Config

`web/.env.example` (both values are public):

```
VITE_API_BASE_URL=https://<stable backend domain>   # serves /api/v1/, no trailing slash
VITE_GITHUB_CLIENT_ID=<GitHub OAuth app client id>
```

If either is missing, don't render the **Get key** button. The landing page must work exactly as today without them.

### 2.3 Header button

Add a **Get key** button to the header bar, next to the GitHub icon. It opens the dialog.

### 2.4 Dialog states

`signin → (GitHub) → signing-in → keys | create → issued`

| State | Shows | Actions |
|---|---|---|
| `signin` | "Authenticate yourself using GitHub" | **Continue with GitHub** |
| `signing-in` | Spinner: "Signing you in…" | none |
| `keys` | User's keys: name, project, created date (never a key) | **Rotate** (confirm: "Agents using the old key will stop working"), **Revoke** (confirm), **New key** |
| `create` | Repository picker of the user's public repos from `GET /api/v1/github/repos/` (repos that already have a key disabled), with **Use a different URL** for a typed URL (placeholder `https://github.com/you/repo`); falls back to the URL field if GitHub can't be reached or lists nothing; Key name (default: the selected agent's name) | **Create key** |
| `issued` | The key with **Copy**; "Save it now. It won't be shown again."; the project it was saved under (canonical ID from the response); the connect text for the agent selected on the page with `ck_...` replaced by the real key, with **Copy** | **Done** (goes to `keys`) |

After sign-in, fetch `GET /api/v1/clients/`. An empty list goes straight to `create`; otherwise show `keys`.

### 2.5 GitHub redirect and return

**Leaving:**
- Generate `state` with `crypto.getRandomValues` (32 bytes, base64url).
- Save to `sessionStorage`: `ck_oauth_state`, `ck_oauth_return = "get-key"`, and the selected agent index.
- Navigate to:
  ```
  https://github.com/login/oauth/authorize?client_id=<VITE_GITHUB_CLIENT_ID>&redirect_uri=<origin>/&state=<state>&allow_signup=true
  ```
  Don't send a `scope` parameter.

**Returning** (on app load, if the URL has `code` and `state`):
1. Read the `sessionStorage` values, then delete them immediately: they are single-use.
2. Strip `code` and `state` with `history.replaceState` **before** any network call.
3. If there was no `ck_oauth_return` value, ignore the code and don't open the dialog.
4. Open the dialog in `signing-in`, and restore the selected agent.
5. If `state` doesn't match, show "Sign-in expired or was interrupted. Please try again." and go back to `signin`.
6. Otherwise `POST /api/v1/auth/github/ {code, redirect_uri: <origin>/}` and keep `access` in memory. Ignore `refresh`.

**GitHub sends the user back with `?error=access_denied`:** strip the URL, reopen the dialog and show "GitHub sign-in was cancelled."

**`redirect_uri`** must be exactly the same string in the authorize URL and the backend call, and must match the GitHub OAuth app's callback URL.

### 2.6 `api.ts`

- Remove `logIn` (password).
- Add:
  - `signInWithGitHub(code, redirectUri) → access token`
  - `listKeys(token)`
  - `createKey(token, projectUrl, name)` (exists)
  - `rotateKey(token, id)`
  - `revokeKey(token, id)`
- **401 on any keyed call:** drop the token and go back to `signin` with "Your sign-in expired. Please sign in again."
- **Error messages by status:**
  - 400 from `auth/github/`: the server's message;
  - 403: "This GitHub account isn't allowed to sign in.";
  - 503: "GitHub sign-in isn't set up on the server.";
  - 429 and network errors: keep the existing messages.

### 2.7 Security rules

- No JWT, key, or GitHub code in `localStorage`, cookies or URLs. `sessionStorage` holds only the three values in 2.5, and only until the user returns.
- Closing the dialog clears the token, the key list and any issued key.
- Never log the key or the token to the console.

### 2.8 Verification

The web app has no test framework, so verify by hand. **Manual testing runs entirely on local SQLite files, never on the Supabase database in `.env`.**

**Ports** (fixed, because 5173 and 8000 are taken on the developer's machine): website `5180`, Django `8010`, MCP server `8011`.

**1. Environment.** In every terminal used for the checks (Django, MCP server, migrations):

```bash
export DATABASE_URL=""                 # set but empty: .env's Supabase URL is then NOT loaded
export CONTEXTKIT_ALLOW_SQLITE=true
export CONTEXTKIT_DB_PATH=~/.contextkit-manual/core.sqlite3
export DJANGO_DB_PATH=~/.contextkit-manual/django.sqlite3
export CONTEXTKIT_HOSTED=true          # the same auth path as Render
mkdir -p ~/.contextkit-manual
```

`DATABASE_URL` must be **exported as an empty string**, not unset: `.env` is loaded with python-dotenv, which doesn't override a variable that is already set, but does fill in one that is missing.

**2. Safety check, before running anything else.** This must print a `sqlite:///…/.contextkit-manual/…` URL. If it prints anything else, stop.

```bash
python3 -m uv run python -c "from core.config import resolve_database_url, resolve_django_database_url as d; print(resolve_database_url()); print(d())"
```

**3. Databases.**

```bash
python3 -m uv run alembic upgrade head
cd api && python3 -m uv run --extra backend python manage.py migrate && cd ..
```

**4. Servers.**
- **Django** (in `api/`), with `DJANGO_SECRET_KEY=manual-test`, `DJANGO_DEBUG=true`, `DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:5180`, and `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` from a **separate development** GitHub OAuth app whose callback URL is `http://localhost:5180/`:
  `python3 -m uv run --extra backend python manage.py runserver 127.0.0.1:8010`
- **MCP server** (repo root): `python3 -m uv run fastmcp run server.py:mcp --transport http --host 127.0.0.1 --port 8011`
- **Website** (`web/`), with `VITE_API_BASE_URL=http://127.0.0.1:8010` and `VITE_GITHUB_CLIENT_ID=<dev app id>` in `web/.env.local`:
  `npm run dev -- --port 5180 --strictPort`

Ask the developer before creating or using the development GitHub OAuth app.

**5. Checks.**

- `npm run build` and `npm run lint` pass.
- With no env vars: no **Get key** button, and the page is unchanged.
- **New user:** sign in, create a key, the key shows once, and the command contains it. The project shown is canonical even when the input was `git@…:….git`.
- **The key works** against the local MCP server, registered under a separate name so the real `contextkit` server isn't touched:
  `claude mcp add --transport http contextkit-local http://127.0.0.1:8011/mcp --header "Authorization: Bearer <key>"`, then `get_context` succeeds. Remove it afterwards with `claude mcp remove contextkit-local`.
- **Returning user:** the key list shows. Rotate makes the old key fail and the new one work. Revoke removes the key.
- **Duplicate:** the same repo in another URL form shows the "Rotate it instead" message.
- **State check:** a tampered `state` in the URL shows the expired message and creates no session.
- **Address bar:** contains no `code` after return; Back doesn't replay sign-in.
- **Mobile width:** the dialog is usable.
- **Supabase untouched:** nothing in the checks above wrote to the database in `.env`. Delete `~/.contextkit-manual/` when done.

---

## Part 3 — Runtime config (`/config.json`)

**Added:** 2026-10-03

### 3.1 Why

The backend is reached through a Cloudflare quick tunnel for now, and its URL changes whenever the tunnel restarts. Today the URL is baked into the website at build time (`VITE_API_BASE_URL` in `web/src/api.ts`), so every restart means a rebuild and redeploy. Reading the two public settings from a file at runtime turns that into editing one file.

### 3.2 The file

Served from the website's own origin at `/config.json`:

```json
{
  "apiBaseUrl": "https://<tunnel or domain>",
  "githubClientId": "<GitHub OAuth app client id>"
}
```

- Both values are public. **Never** put the GitHub client secret, a key, or anything else secret in it: everyone who visits the site can read it.
- Commit `web/public/config.example.json` with placeholder values.
- Add `web/public/config.json` to `.gitignore`. Each deployment provides its own copy.
- Unknown fields are ignored.

### 3.3 Loading and precedence

- New `web/src/config.ts`:
  - `loadConfig(): Promise<void>` fetches `/config.json` once with `cache: 'no-store'`, so a changed URL takes effect on the next page load.
  - It times out after **3 seconds**.
  - Use `fetch` with a relative path only: the site never loads config from another origin or from a URL parameter. Otherwise a crafted link could point the dialog at someone else's backend.
- **Precedence per field:**
  1. a valid value in `config.json`;
  2. otherwise the build-time `VITE_*` variable (keeps local development with `web/.env.local` working);
  3. otherwise empty.
- **Validation:**
  - `apiBaseUrl` must parse as a URL with `https:`. The one exception is `http:` on `localhost` or `127.0.0.1`. Strip trailing slashes.
  - `githubClientId` must match `^[A-Za-z0-9._-]{1,100}$`.
  - An invalid value is ignored with a `console.warn` naming the field (the values are public, so naming them is fine).
- **Failure never breaks the page.** A missing file (404), invalid JSON, a network error or the timeout all fall back to the build-time values. If neither source gives both values, `isConfigured()` is false and the **Get key** button stays hidden, exactly as today.
- `web/src/api.ts`: replace the module-level `BASE_URL` / `GITHUB_CLIENT_ID` constants with getters from `config.ts`, so every call reads the loaded values. `oauth.ts` uses the client ID the same way.
- `web/src/main.tsx`: render only after `loadConfig()` settles (resolved or failed). `App`'s synchronous `isConfigured()` checks, including reopening the dialog when GitHub sends the user back, then see the final config. The 3-second timeout caps the delay.

### 3.4 Docs

- `web/README.md`: document `config.json` (fields, precedence, "public values only", a no-cache header on the host).
- `web/.env.example`: note that `config.json` overrides these values in deployments.

### 3.5 Verification (manual; the web app has no test framework)

- `npm run build` and `npm run lint` pass.
- No `config.json` and no `VITE_*`: no **Get key** button; the page is unchanged.
- `config.json` only (no `VITE_*`): the button appears, and sign-in and key creation call the URL from the file.
- Both present: `config.json` wins.
- Change `apiBaseUrl` in the served `config.json` and reload **without rebuilding**: requests go to the new URL.
- Invalid JSON, an `http://` non-localhost URL, or a bad client ID: ignored with a warning, falling back to the build-time values.
- With a 5-second delay on `config.json` (DevTools throttling or a slow local server), the page renders after about 3 seconds using the fallback.
- **GitHub return:** after signing in, the dialog still reopens and signs in, with config loaded asynchronously first.
- **One request per load:** the Network tab shows one `config.json` request per page load, not cached.

### 3.6 Out of scope

- Updating `config.json` automatically when the tunnel restarts. That's an operations script on EC2 that reads the new URL from `cloudflared` and writes the file.
- Serving the website and the API from one origin.
- Any secret in the config.

---

## Deploy prerequisites (developer, not the coding session)

1. **Give the Django backend a stable public URL** (a named Cloudflare tunnel or a domain on Traefik). The quick-tunnel URL changes on every restart.
2. **GitHub OAuth app:** set the callback URL to the website's origin plus `/`. Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` on the backend.
3. **Backend:** `DJANGO_CORS_ALLOWED_ORIGINS=<website origin>`.
4. **Website settings:** deploy `/config.json` (Part 3) with `apiBaseUrl` and `githubClientId`, served with `Cache-Control: no-store`. Choose a website host where this file can be changed without rebuilding the site, e.g. an nginx container on EC2 with the file mounted. When the tunnel restarts, update `apiBaseUrl`; nothing else changes. GitHub OAuth and `DJANGO_CORS_ALLOWED_ORIGINS` depend on the website's address, not the backend's. Also allow the tunnel host in `DJANGO_ALLOWED_HOSTS` (`.trycloudflare.com` survives restarts). `VITE_*` build variables remain a fallback.
5. **Run both migrations before the new code serves traffic:**
   - `alembic upgrade head`
   - `cd api && python manage.py migrate`
   Then redeploy the MCP server on Render and the backend on EC2. If the Django migration reports a collision, revoke one of the named clients and rerun.

   **Keep the gap short.** Between the migrations and the Render redeploy, the old MCP code compares the raw `project_id` an agent sends with the now-canonical client project, so agents that send their own `project_id` are refused (agents that omit it keep working). Run the migrations and trigger the Render deploy back to back.

---

## Implementation checklist

- [ ] 1.1 `core/projects.py` + tests
- [ ] 1.2 normalization applied in validation, local detection, the auth check and client creation; duplicate message
- [ ] 1.3 Alembic 0004 and Django 0002 data migrations + tests
- [ ] 1.4 all backend tests green: `pytest` and `cd api && python manage.py test`
- [ ] 2.1–2.2 dialog restored, config, button hidden when unconfigured
- [ ] 2.3–2.6 header button, states, GitHub redirect and return, API calls
- [ ] 2.7 security rules checked
- [ ] 2.8 manual verification done on local SQLite, `npm run build` and `npm run lint` pass
- [ ] ADR 030 (`docs/ADR/030-get-key-from-website.md`, currently untracked) committed with the feature
- [x] 3.2–3.3 `config.ts`, `config.example.json`, `.gitignore`, `api.ts`/`oauth.ts` getters, render after `loadConfig()`
- [x] 3.4 `web/README.md` and `web/.env.example` updated
- [x] 3.5 manual checks done, `npm run build` and `npm run lint` pass

---

## Success criteria

- A first-time user goes from **Get key** to a working key in one dialog, with one trip to GitHub.
- Any URL form of a repository resolves to the same project for both key creation and agent calls.
- Existing projects and clients are migrated with no lost history, and no key is silently deleted.
- No secret is persisted in the browser or exposed in a URL.
- The site is unchanged when the key feature isn't configured.

---

## Out of scope

- Per-user keys.
- Private or organisation repositories in the picker (needs a GitHub App).
- A dashboard page.
- Rate limiting key creation.
- Changing the existing endpoints' URLs or auth.
- The password sign-in endpoint (stays for scripts; just not used by the website).
