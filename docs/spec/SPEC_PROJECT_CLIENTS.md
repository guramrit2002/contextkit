# Implementation Spec: Projects own many clients

**Created:** 2026-10-04
**Status:** Ready for implementation. **Part A is urgent** (an open security hole on the live user API).
**Context:** ADR 031 (read it first), ADR 022, 025, 028, 030

---

## Overview

The model to implement:

```
User ──owns──▶ Project ──has many──▶ Client (one per agent) ──has one──▶ API key
```

| Part | What | Ships |
|---|---|---|
| **A — Ownership (urgent)** | A user may create a client only for a project they own: no other user holds clients for it, and for `github.com` projects GitHub confirms they own the repo. Plus a check that reports projects already shared between users. | Backend only. Deploy on its own, first. |
| **B — Many clients per project** | Drop the one-client-per-user-per-project rule and tell clients apart by name; the website groups keys by project with **Add agent**. | Backend migration, then the website. |

**Decisions already made (don't revisit):**
- Ownership is derived from existing clients; there's no new table.
- Only public repositories owned by the user's own GitHub login. Organisation, private and non-GitHub repositories are refused through the user API.
- Operator paths (Django admin, `manage.py create_client`) skip the GitHub check but keep the one-owner rule.
- No team sharing.
- Core does not change.

---

## Part A — Ownership (urgent)

### A.1 GitHub repository lookup: `api/accounts/github.py`

Add `fetch_public_repo(full_name: str) -> GitHubRepoOwner | None`:
- Calls `GET https://api.github.com/repos/{owner}/{repo}` with the existing `_app_credentials()` and `Accept: application/vnd.github+json`. No user token and no new scope.
- Returns `None` on 404. A private repository is also 404 to app credentials.
- Raises `GitHubAuthError` on network errors and on other non-2xx responses.
- Returns `owner.login`, the owner's `type` (`User`/`Organization`) and `private` from the response.
- Reuse `_request`, `TIMEOUT_SECONDS` and the error style already in that module.

`_request` currently raises on HTTP errors through `URLError` (`HTTPError` is a subclass). Catch `urllib.error.HTTPError` with code 404 to return `None`, and leave other codes raising.

### A.2 The ownership rules: `api/clients/services.py`

New messages:
```python
OTHER_OWNER_MESSAGE = "This repository is registered to another account."
NOT_YOUR_REPO_MESSAGE = "You can only create keys for public repositories you own on GitHub."
GITHUB_UNAVAILABLE_MESSAGE = "Could not check the repository on GitHub. Try again."
```

**`ensure_single_owner(user_id, project_id)`:**
- If any `Client` with this `project_id` has a different `user_id`, raise `ValidationError({"project_id": [OTHER_OWNER_MESSAGE]})`.
- Don't reveal the other user.

**`ensure_owns_on_github(user, project_id)`** applies to canonical IDs whose host is `github.com`:
- Parse `https://github.com/<owner>/<repo>` from the canonical ID (`core.projects` already lowercases GitHub paths). Any other shape for `github.com`, such as a missing repo segment or extra segments, gets `NOT_YOUR_REPO_MESSAGE`.
- Look up `accounts.GitHubIdentity` for `user`. If there's none, raise `NOT_YOUR_REPO_MESSAGE`.
- Call `github.fetch_public_repo(f"{owner}/{repo}")`:
  - `None` → `NOT_YOUR_REPO_MESSAGE`;
  - `GitHubAuthError` → `GITHUB_UNAVAILABLE_MESSAGE`;
  - `private` → `NOT_YOUR_REPO_MESSAGE`;
  - `owner.login.lower() != identity.login.lower()` → `NOT_YOUR_REPO_MESSAGE`. This also covers organisation owners.
- If GitHub sign-in isn't configured (`github.is_configured()` false), refuse with `NOT_YOUR_REPO_MESSAGE`. Never skip the check.

**Projects that aren't on `github.com`** (other hosts, folder paths) are refused through the user API with `NOT_YOUR_REPO_MESSAGE`, because ownership can't be proven.

**Where each rule applies:**

| Path | One-owner rule | GitHub ownership |
|---|---|---|
| `create_client_for_user` (user API and website) | yes | yes |
| `create_client` (admin, `manage.py create_client`) | yes | no (trusted operator) |
| `rotate_client_key`, `revoke_client` | no change; they already require the caller's own client | no |

Order inside `create_client_for_user`:
1. canonicalize the project ID (existing `canonical_project_id`);
2. one-owner rule;
3. GitHub ownership;
4. the existing create.

Do the GitHub call **outside** the database transaction. Put the one-owner check inside `create_client`'s `transaction.atomic` too, so the admin path enforces it.

**Imports:** Django apps may import each other. `clients` importing `accounts` is fine; core still imports nothing from Django.

### A.3 Views

`ClientListView.post` already maps a Django `ValidationError` to 400. Make sure all three messages come back under `project_id` with status 400. Don't add a 403 status: the web client already shows field errors from 400.

### A.4 Report existing shared projects: `api/clients/checks.py`

Add `clients.W002`, registered with `checks.Tags.database` next to `W001`:
- lists each `project_id` whose clients have more than one distinct `user_id`, with the client ids and names;
- **reports only, never changes data.** Its hint: "Review these projects and revoke the clients that don't belong to the project owner."

### A.5 Tests

**`api/accounts/tests.py`**, for `fetch_public_repo`:
- 200 public returns the owner;
- 404 returns `None`;
- a 500 or a network error raises.

Patch `urllib.request.urlopen` the way existing tests do.

**`api/clients/test_api.py`**, with `github.fetch_public_repo` patched:
- the owner creates a key for their own public repo → 201;
- the repo is owned by another login → 400 with `NOT_YOUR_REPO_MESSAGE`;
- an organisation-owned repo → 400;
- a private repo or 404 → 400;
- GitHub unreachable → 400 with `GITHUB_UNAVAILABLE_MESSAGE`, and **no client created**;
- the user has no `GitHubIdentity` → 400;
- a non-GitHub URL or folder path → 400;
- **the reported attack:** user B tries the canonical ID of user A's project, where A already has a client → 400 with `OTHER_OWNER_MESSAGE`, even if B's GitHub check were mocked to pass;
- **any URL form** of a repo (`git@…`, `.git`, mixed case) passes or fails the same way.

**`api/clients/tests.py`:**
- `create_client` (operator path) skips GitHub but enforces the one-owner rule;
- the admin form shows the one-owner error;
- `W002` lists a shared project and is silent otherwise.

**Existing tests** that create clients through the user API need the GitHub patch. Add one fixture or helper rather than patching in every test.

### A.6 Deploy Part A alone (developer)

1. Merge Part A into `dev`.
2. On EC2: `git pull`, `docker compose build`, `docker compose up -d`. Part A has no migration.
3. Run `docker compose run --rm api python manage.py check --database default`. If `clients.W002` lists projects, review them and revoke the clients that don't belong.
4. Confirm from outside: a key request for someone else's repo now returns 400.

---

## Part B — Many clients per project

### B.1 Model and migration: `api/clients`

- `Client.Meta.constraints`:
  - remove `uniq_client_user_project`;
  - add `UniqueConstraint(Lower("name"), "user_id", "project_id", name="uniq_client_user_project_name")`.
- `Client.project_id` `help_text`: "The project this client works on (canonical repository URL)."
- New migration `0003_clients_per_project.py`: drop the old constraint, add the new one. Existing rows satisfy it (at most one client per user and project today). Keep it reversible: the reverse re-adds the old constraint and fails clearly if data now violates it.
- `name`: required. Strip it, and reject an empty name after stripping.

### B.2 Services: `api/clients/services.py`

- Replace `DUPLICATE_PROJECT_MESSAGE` and its check with a name check:
  - if the user already has a client for this project with the same name (case-insensitive), raise `ValidationError({"name": ["This project already has a key named <name>. Rotate it, or choose another name."]})`.
- Part A's ownership rules stay, in the same order: canonicalize, one-owner, GitHub, then the name check.
- Update the comment that cites "each has one key (ADR 022)" to reference ADR 031.
- The admin form (`ClientAdminForm`): normalization stays; the duplicate error now comes from the name constraint.

### B.3 API

No new endpoints. `GET /api/v1/clients/` still returns a flat list (`id`, `name`, `project_id`, `created_at`, `updated_at`, `has_key`). The website groups it.

### B.4 Website: `web/src/ApiKeyModal.tsx`

**`keys` step:** group keys by `project_id`, with projects ordered by their most recent key.
- **Project heading:** the project without the `https://` prefix, e.g. `github.com/you/app`.
- **Under it,** one row per client: name, created date, **Rotate**, **Revoke**. Keep the existing inline confirmations.
- **Per project,** an **Add agent** button. It opens `create` with that project **fixed**: no picker, the project shown as text. The name defaults to the agent selected on the page (`setup.agent`). If that name is taken in this project, default to `"<agent> 2"`, `"<agent> 3"`, and so on, and let the user edit it.
- **New project**, replacing **New key**: opens `create` with the picker, as today. The name defaults to the selected agent.

**`create` step:**
- **Field errors:** show `project_id` errors under the repository and `name` errors under the name. `ApiError` already carries the server message; keep that behavior.
- **Intro text:** "One key per agent. Add one for each tool you use on this project."
- **Typed URL:** keep the "Use a different URL" fallback. The server now enforces ownership.

**`issued` step:** unchanged. It shows the key once and the connect text for the selected agent.

**`FEATURES` in `web/src/App.tsx`:** change "One project per key" to "One key per agent".

### B.5 Tests and checks

**Django:**
- a second client for the same project with a different name → 201;
- the same name with different case → 400 under `name`;
- rotating one client leaves the other's key working; check this through `core.auth.authenticate_client` against both keys;
- revoking one client leaves the other working;
- `audit_log` and decisions record the correct `client_id` per key;
- the migration applies on a database with existing clients.

**Core:** no changes. The existing `pytest` suite must still pass.

**Web** (no test framework; manual on the local stack):
- `npm run build` and `npm run lint` pass;
- grouping;
- **Add agent** with a fixed project;
- the automatic "<agent> 2" naming;
- the duplicate-name error shown under the name;
- rotate and revoke act on one agent only;
- **New project** still uses the picker.

### B.6 Deploy Part B (developer)

1. Merge into `dev`.
2. On EC2: `git pull`, `docker compose build`, then `docker compose run --rm migrate` (applies `clients 0003`), then `docker compose up -d`.
3. Vercel redeploys the website from `dev`; nothing to configure.
4. Render needs no change: core is untouched.

---

## Safety rules for the coding session

- Tests run on SQLite (`CONTEXTKIT_ALLOW_SQLITE`, ADR 029). **Never** run tests, migrations or management commands against `DATABASE_URL` from `.env`, which is production Supabase.
- Patch every GitHub call in tests. No test may reach `api.github.com`.
- Never print keys, tokens, client secrets or database URLs.

---

## Implementation checklist

**Part A**
- [x] A.1 `fetch_public_repo` + tests
- [x] A.2 `ensure_single_owner`, `ensure_owns_on_github`, wired as in the table
- [x] A.3 400 responses with the three messages
- [x] A.4 `clients.W002`
- [x] A.5 tests; `pytest` and `cd api && python manage.py test` pass
- [x] Part A committed and pushed on its own branch, ready to deploy alone

**Part B**
- [x] B.1 constraint change + migration `0003`
- [x] B.2 name-based duplicate check
- [x] B.4 dialog grouped by project, Add agent, New project, field errors, FEATURES text
- [x] B.5 Django tests; `npm run build` and `npm run lint`; manual web checks
- [x] ADR 031 committed with Part A

---

## Success criteria

- Nobody can create a key for a repository they don't own on GitHub, or for one already registered to another account. Verified against the live API after deploy.
- A user can hold separate keys for Claude Code, Codex and Cursor on one project. Each can be rotated or revoked alone, and each is attributed separately in `audit_log`.
- No existing client or key is changed or deleted by the migration or the checks.
- Core and the MCP server are unchanged.

---

## Out of scope

- Team sharing and invitations.
- A GitHub App for organisation and private repositories.
- A `project_owners` table.
- Changes to core, the MCP tools or the agent REST API.
- Per-key rate limiting.
