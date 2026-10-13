# Coding Agent Prompt: Projects own many clients

**Status:** Ready. Part A is urgent.
**Spec:** `docs/spec/SPEC_PROJECT_CLIENTS.md`
**ADR:** `docs/ADR/031-projects-own-many-clients.md`

Copy everything in the block below into a fresh coding session.

---

```
You are implementing a feature for contextkit based on a written spec. Read
everything below before writing any code.

## 1. Project rules

Read `docs/CLAUDE.md`. Its rules are non-negotiable:
- `core/` has no framework imports.
- Business logic lives in services.py.
- Django writes context only through core.

This task doesn't touch core at all.

## 2. Your spec

Read `docs/spec/SPEC_PROJECT_CLIENTS.md` in full. It has two parts. Do them
in order, on separate branches:

- Part A (urgent, security): only the owner of a project may create keys
  for it. A user may create a client only if no other user holds clients for
  that project and, for github.com projects, GitHub confirms they own the
  public repo. Also add the clients.W002 check. Backend only, no migration.
  Today anyone can create a key for someone else's repo and read its
  context, on the live API.
- Part B: a project can have many clients (one per agent), told apart by
  name. A constraint migration, plus the website dialog grouped by project
  with "Add agent".

## 3. Architecture decisions

Read `docs/ADR/031-projects-own-many-clients.md`, and skim ADR 022, 025, 028
and 030. Don't change those decisions.

## 4. Existing code to reuse

- api/clients/services.py: canonical_project_id, create_client,
  create_client_for_user, rotate_client_key, revoke_client, owner_id
- api/clients/models.py: Client (constraint uniq_client_user_project), ApiKey
- api/clients/checks.py: clients.W001 (copy its pattern for W002)
- api/clients/admin.py: ClientAdminForm
- api/accounts/github.py: _request, _app_credentials, list_public_repos,
  GitHubAuthError
- api/accounts/models.py: GitHubIdentity (login per Django user)
- core/projects.py: normalize_project_id (github.com paths are lowercased)
- web/src/ApiKeyModal.tsx (steps signin/keys/create/issued), web/src/api.ts,
  web/src/setups.ts, and FEATURES in web/src/App.tsx
- Tests: api/clients/test_api.py, api/clients/tests.py,
  api/accounts/tests.py, api/clients/test_user_deletion.py

## 5. Environment notes

- Branches from origin/dev, in the main checkout (docs/spec, docs/prompts
  and .claude are gitignored, so a fresh worktree lacks them):
  - Part A: fix/project-ownership
  - Part B: feature/clients-per-project, branched after Part A is merged,
    or from Part A's branch if it isn't merged yet
  dev is the default branch; there is no main. Push the branches; the
  developer opens the PRs.
- Commit docs/ADR/031-projects-own-many-clients.md with Part A.
- Tests use SQLite via CONTEXTKIT_ALLOW_SQLITE (ADR 029). NEVER run tests,
  migrations or management commands against DATABASE_URL in .env: it is
  production Supabase.
- Patch every GitHub call in tests; nothing may reach api.github.com.
- Never print keys, tokens, client secrets or database URLs.
- uv is at ~/Library/Python/3.9/bin/uv if needed.
- Commit messages follow .claude/commit_template.txt. Do NOT add any
  Co-Authored-By or Claude attribution line.

## 6. Implementation rules

- Part A must be complete, tested and pushed before you start Part B.
- Never delete or change existing clients or keys in code, migrations or
  checks. W002 only reports.
- The GitHub check must fail closed. If GitHub is unreachable or sign-in
  isn't configured, refuse to create the key; never skip the check.
- Don't add scope beyond the spec. Its "Out of scope" list is binding.
- If the spec is ambiguous or conflicts with docs/CLAUDE.md, stop and ask.

## 7. Before you finish

- `pytest` and `cd api && python manage.py test` pass after each part.
- Part B: `cd web && npm run build && npm run lint` pass, and the manual web
  checks in spec B.5 are done on a local SQLite backend. Ask the developer
  before using a real GitHub OAuth app.
- Report for each part:
  - what you built;
  - any deviation from the spec and why;
  - what's left;
  - the exact deploy steps (spec A.6 and B.6).

Start by reading docs/CLAUDE.md, then the spec, then ADR 031, then begin
with Part A.
```
