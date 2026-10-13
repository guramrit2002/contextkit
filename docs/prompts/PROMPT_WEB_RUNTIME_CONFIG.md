# Coding Agent Prompt: Website runtime config

**Status:** Ready
**Spec:** `docs/spec/SPEC_GET_KEY_FROM_WEBSITE.md`, **Part 3 only**
**ADR:** `docs/ADR/030-get-key-from-website.md`

Copy everything in the block below into a fresh coding session.

---

```
You are making a small change to the contextkit website (web/) based on a
written spec. Read everything below before writing any code.

## 1. Your task

Read Part 3 of `docs/spec/SPEC_GET_KEY_FROM_WEBSITE.md` ("Runtime config").
Parts 1 and 2 are already built and merged; don't change them except where
Part 3 says.

Goal: the website reads its two public settings (backend URL, GitHub OAuth
client ID) from /config.json at runtime, falling back to the build-time
VITE_* variables. This way a change of backend URL (the Cloudflare quick
tunnel restarts) needs only an edit to that file, not a rebuild.

## 2. Code to change

- web/src/api.ts: BASE_URL and GITHUB_CLIENT_ID are module-level constants
  read from import.meta.env. Turn them into getters backed by a new
  web/src/config.ts.
- web/src/oauth.ts: use the same getter for the client ID.
- web/src/main.tsx: render after loadConfig() settles (3-second timeout).
- App.tsx calls isConfigured() synchronously, including when GitHub sends
  the user back. Keep it synchronous by loading config before render.
- Add web/public/config.example.json, ignore web/public/config.json in
  .gitignore, and update web/README.md and web/.env.example.

## 3. Rules from the spec

- Fetch /config.json from the site's own origin only (relative path,
  cache: 'no-store'). Never take the config location from a URL parameter.
- Validate both fields: https URL (http only for localhost or 127.0.0.1),
  client ID ^[A-Za-z0-9._-]{1,100}$. Ignore invalid values with a warning.
- A missing file, invalid JSON, a network error or the timeout must never
  break the page. Fall back to VITE_*, else hide the Get key button as today.
- Nothing secret goes in config.json. Don't change the in-memory handling
  of the JWT and keys.

## 4. Environment notes

- Work on a new branch from origin/dev in the main checkout (docs/spec,
  docs/prompts and .claude are gitignored, so a fresh worktree lacks them).
  dev is the default branch; push the branch, and the developer opens the PR.
- This is a web-only change; don't touch the backend or any database.
- If you test the full sign-in flow, ask the developer first: the local
  backend on 127.0.0.1:8010 currently points at production Supabase, so keys
  created there are real.
- Commit messages follow .claude/commit_template.txt. Do NOT add any
  Co-Authored-By or Claude attribution line.

## 5. Before you finish

- `cd web && npm run build && npm run lint` pass.
- Do the manual checks in spec §3.5. Serve web/dist with a local static
  server where you can add, edit and delay config.json.
- Tick the Part 3 items in the spec's checklist.
- Report what you built, any deviation from the spec and why, and what the
  developer must do to deploy config.json.

Start by reading the spec's Part 3, then web/src/api.ts, oauth.ts, main.tsx
and App.tsx.
```
