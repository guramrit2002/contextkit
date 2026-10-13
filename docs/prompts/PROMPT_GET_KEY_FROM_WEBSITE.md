# Coding Agent Prompt: Get an API key from the website

**Status:** Ready
**Spec:** `docs/spec/SPEC_GET_KEY_FROM_WEBSITE.md`
**ADR:** `docs/ADR/030-get-key-from-website.md`

Copy everything in the block below into a fresh coding session.

---

```
You are implementing a feature for contextkit based on a written spec. Read
everything below before writing any code.

## 1. Project rules

Read `docs/CLAUDE.md`. Its rules are non-negotiable:
- `core/` has no framework imports.
- MCP tools are thin wrappers.
- Only core writes the context tables.
- Django writes context only through core.
- Business logic lives in services.py.

## 2. Your spec

Read `docs/spec/SPEC_GET_KEY_FROM_WEBSITE.md` in full. It has two parts. Do
them in order:

1. Project-ID normalization in the backend: `core/projects.py`, applying it
   wherever a project ID enters, and data migrations for core and Django.
2. The "Get key" dialog in `web/`, with GitHub sign-in.

## 3. Architecture decisions

Read `docs/ADR/030-get-key-from-website.md`. Also skim:
- ADR 012 (project identification, which ADR 030 implements);
- ADR 022 (one client per project);
- ADR 028 (the user API and GitHub sign-in that already exist).

Don't change those decisions.

## 4. Existing code to reuse

- Backend endpoints already exist. Don't change their URLs or auth:
  - api/accounts/ (GitHub sign-in: github.py, services.py, views.py)
  - api/clients/ (services.py, views.py, serializers.py)
- Project ID touch points:
  - core/redaction.py validate_project_id
  - core/storage.py detect_project_id, get_or_create_project
  - core/auth.py validate_client_project_access
  - api/clients/services.py create_client
- Migration test patterns: tests/test_migrations.py
- The removed key dialog: restore it with `git show 8245771^:<path>` for
  web/src/ApiKeyModal.tsx, web/src/api.ts, web/src/vite-env.d.ts,
  web/.env.example and the dialog CSS in web/src/index.css. Keep its
  patterns: native <dialog>, the JWT in memory only, ApiError messages, and
  the copy buttons. Replace password sign-in with GitHub as the spec
  describes.
- Agent connect texts: the SETUPS array in web/src/App.tsx.

## 5. Environment notes

- Work on a new branch from origin/dev, in the main checkout, not a separate
  git worktree: docs/spec/, docs/prompts/ and .claude/ are gitignored, so a
  fresh worktree has no spec, prompt or commit template. dev is the default
  branch; there is no main. Push the branch; the developer opens the PR.
- Commit docs/ADR/030-get-key-from-website.md (currently untracked) with the
  feature.
- Tests use SQLite through CONTEXTKIT_ALLOW_SQLITE (ADR 029). Never run tests,
  migrations or servers against the DATABASE_URL in .env, which is production
  Supabase.
- Manual testing also runs on local SQLite only. Follow spec §2.8 exactly:
  export DATABASE_URL as an EMPTY string (unset is not enough: .env would
  fill it back in), run its safety check, and stop if it prints anything but
  a sqlite URL. Use ports 5180 (web), 8010 (Django) and 8011 (MCP); 5173 and
  8000 are taken. Register the local MCP server as contextkit-local, never
  over the existing contextkit server.
- uv is at ~/Library/Python/3.9/bin/uv if you need it.
- Web: `cd web && npm run build && npm run lint`. There's no web test
  framework; do the manual checks in spec §2.8.
- Commit messages follow .claude/commit_template.txt. Do NOT add any
  Co-Authored-By or Claude attribution line.

## 6. Implementation rules

- Follow the spec's checklist in order. Normalization and its migrations
  come before any web work.
- Data migrations must never delete a client or key. On a collision they
  raise, as the spec says.
- Do not break existing behavior. All existing tests must pass.
- Don't add scope beyond the spec. Its "Out of scope" list is binding.
- If the spec is ambiguous or conflicts with docs/CLAUDE.md, stop and ask.

## 7. Before you finish

- `pytest` and `cd api && python manage.py test` pass.
- `cd web && npm run build && npm run lint` pass.
- Do the manual checks in spec §2.8 against the local SQLite backend. Ask the
  developer before creating or using the development GitHub OAuth app.
- Report:
  - what you built;
  - any deviation from the spec and why;
  - what's left;
  - the deploy prerequisites the developer still has to do (spec
    "Deploy prerequisites").

Start by reading docs/CLAUDE.md, then the spec, then ADR 030, then begin.
```
