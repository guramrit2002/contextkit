# ADR 030 — Get an API key from the website with GitHub sign-in

**Status:** Proposed

**Amends:** ADR 012 (project identification), ADR 028 (user API)

## Context

ADR 028 built everything a user needs to get a key without an operator: GitHub sign-in (`POST /api/v1/auth/github/`) and self-service clients (`/api/v1/clients/`). The website briefly had a key dialog (`1cb95ac`), using username-and-password sign-in, but it was removed in `8245771` because keys were not to be issued from the website yet. Today a user can only get a key by hand.

The intended experience is one flow on the website: click **Get key**, sign in with GitHub, come back to the same dialog, and copy the key.

Two things stand in the way:

1. **A key belongs to one project** (ADR 022), so the dialog must ask which repository the key is for.
2. **Project IDs are compared as raw strings.** ADR 012 says remotes are normalized, but the code never did it. If a user types `https://github.com/me/app` and their agent sends `git@github.com:me/app.git`, every call is refused with 403. A self-service flow makes this mismatch routine instead of rare.

## Decision

### The website flow

1. **Get key** in the site header opens a dialog: "Authenticate yourself using GitHub", with a **Continue with GitHub** button.
2. The site stores a random `state` and "reopen the key dialog" in `sessionStorage`, then sends the browser to GitHub's authorize page with no scopes (public profile only, as in ADR 028).
3. GitHub redirects back to the site with `code` and `state`. The site:
   - removes them from the address bar at once;
   - checks `state`;
   - reopens the same dialog.
4. The site posts the code to `/api/v1/auth/github/` and gets a JWT.
5. The dialog shows:
   - for a new user: a **Repository URL** field and a key name;
   - for a returning user: their keys by name and project (never the key itself), with **Rotate**, **Revoke** and **New key**.
6. Creating or rotating shows the key **once** with a Copy button, a "save it now" warning, and the connect command for the agent selected on the page with the key filled in.

A full-page redirect is used, not a popup, because popups are blocked or unreliable on mobile.

The JWT and the key live only in the page's memory and are dropped when the dialog closes. Nothing is written to `localStorage`, and nothing secret goes in a URL. `sessionStorage` holds only the OAuth `state` and the reopen flag, and both are deleted as soon as the user returns. The refresh token is not used by the website: if the access token expires mid-flow, the user signs in again.

### Normalized project IDs

Every project ID is normalized to one canonical form before it is stored or compared. This implements what ADR 012 described.

- Git remotes become `https://<host>/<path>`:
  - `git@host:owner/repo`, `ssh://`, `git://`, `http://` and schemeless `host/owner/repo` are all accepted;
  - credentials, ports, a trailing `.git` and trailing slashes are removed;
  - the host is lowercased, and for `github.com` the whole path is lowercased because GitHub treats owner and repo names case-insensitively.
- Anything that is not a git remote (a folder path) is only trimmed of whitespace and trailing slashes.
- The single implementation is `core.projects.normalize_project_id()`. It is plain Python, so core stays framework-free, and Django calls the same function.
- It is applied:
  - when a client is created;
  - to any `project_id` an agent sends;
  - to the detected project in local mode;
  - on both sides of the client authorization check.
- Existing data is migrated to the canonical form:
  - an Alembic migration for core's tables merges projects that collapse into one;
  - a Django data migration does the same for `clients`.
  - The migrations carry their own frozen copy of the function, so later changes to it can't rewrite history.

## Consequences

- Users get a working key without contacting anyone, in one dialog.
- Any form of a repository URL refers to the same project. This removes the most likely failure in self-service setup.
- Each user still needs one key per repository (ADR 022). Per-user keys remain a separate decision.
- The website is no longer fully static. It needs:
  - `VITE_API_BASE_URL` and `VITE_GITHUB_CLIENT_ID` at build time;
  - its origin listed in `DJANGO_CORS_ALLOWED_ORIGINS`;
  - GitHub OAuth app's callback URL set to the site's origin.
- **The backend needs a stable public URL.** The current Cloudflare quick-tunnel URL changes on every restart, which would break the website's calls and CORS. This must be fixed before the dialog ships.
- Deploys that change project IDs must run both migrations before the new code serves traffic. Otherwise new rows are written under the canonical ID while history sits under the old one.
- If two of a user's clients normalize to the same project, the Django migration stops and names them instead of deleting a key someone may still be using.

## Deferred

- Per-user keys that cover all of a user's repositories.
- Picking a repository from the user's GitHub repos (needs an OAuth scope).
- A dashboard beyond this dialog.
- Rate limiting key creation per user.
