# ADR 031 — A project has many clients, and one owner

**Status:** Proposed

**Amends:** ADR 022 (client authentication), ADR 028 (user API), ADR 030 (get a key from the website)

## Context

The intended model:

```
User ──owns──▶ Project ──has many──▶ Client (one per agent) ──has one──▶ API key
```

- **User:** the person building the project.
- **Project:** their repository, identified by its canonical project ID (ADR 030).
- **Client:** one agent or integration working on it (Claude Code, Codex, Cursor, a CI job).
- **API key:** what that client authenticates with.

Two things in the current code contradict that model.

1. **One client per user per project.** `clients` has a unique constraint on `(user_id, project_id)`, from ADR 022's original "one agent per project". Adding a second agent to a project is refused with "You already have a key for this repository. Rotate it instead." Rotating would cut off the first agent. All of a user's agents would have to share one key, which loses two things:
   - revoking one agent without the others;
   - per-agent attribution in `audit_log`, `decisions.client_id` and `sessions.client_id`.

2. **Nobody owns a project.** Context is keyed only by `project_id`: core reads and writes decisions, state and sessions with `WHERE project_id = …`. Creating a client only checks for a duplicate, and the website accepts any typed URL. So anyone who signs in with GitHub can create a key for **someone else's** repository URL, and then read and write that project's entire context. This is live on the deployed website and user API.

## Decision

### A project has many clients

- Drop `uniq_client_user_project`.
- Add a unique constraint on `(user_id, project_id, lower(name))`. A project's clients are told apart by name, e.g. "Claude Code" or "Codex".
- Each client still belongs to exactly one project and still has exactly one key (ADR 022).
- Rotating or revoking affects only that client.
- Core needs no change: it resolves a key to one client, and the project comes from that client.

### A project has one owner

The owner is the user who holds the project's clients. A user may create a client for a project only if **both** of these hold:

1. **No other user has a client for that project.** Otherwise the request is refused with "This repository is registered to another account." The message doesn't say who.
2. **For a `github.com` project, the user proves ownership on GitHub:**
   - the user has a linked GitHub identity (`accounts.GitHubIdentity`);
   - the repository's owner login equals the user's GitHub login;
   - GitHub confirms the repository exists and is public. The check calls GitHub's repository API with the OAuth app's credentials, as the repository picker already does, and needs no new scope.

   Otherwise: "You can only create keys for public repositories you own on GitHub."

These rules have consequences:
- **Organisation-owned, private and non-GitHub repositories can't get keys through the user API for now.** This is the same limit ADR 030 already accepted for the picker, and a GitHub App remains the planned way to support them.
- **Password-only accounts** (no GitHub identity) can't register GitHub projects through the user API.
- **Operator paths are trusted and skip the GitHub check:** the Django admin and `manage.py create_client`. They still enforce the one-owner rule.
- **The ownership check runs only when a client is created.** Existing clients keep working.
- **A new system check, `clients.W002`,** reports any project whose clients belong to more than one user. It reports only and never deletes, so the operator can review and revoke by hand (the same policy as `clients.W001`).

Ownership is derived from the existing clients, not stored in a new table. For `github.com` projects, two different users can never both pass the GitHub check, so the derived owner is safe without extra locking.

### The website

The key dialog shows keys **grouped by project**:
- each project has an **Add agent** button;
- the new client's name defaults to the agent selected on the page;
- **New project** replaces **New key**.

A typed URL stays available (for example, when GitHub's repository list fails), and the server enforces the ownership rules on it.

## Consequences

- Each agent gets its own key, with separate revocation and attribution, matching the model above.
- Nobody can create a key for another person's repository, which closes the hole.
- Sharing one project between several users (teams) is not possible. That needs an invitation model and a separate ADR.
- Organisation, private and non-GitHub repositories wait for the GitHub App.
- Creating a key now calls GitHub once. If GitHub is unreachable, creation fails with a "try again" message rather than skipping the check.
- If a repository is transferred to another GitHub user, the old owner's clients keep working until revoked. The new owner can't register it while those clients exist. This is an operator decision, surfaced by `clients.W002` only if both end up holding clients.

## Deferred

- Team sharing with invitations.
- A GitHub App for organisation and private repositories.
- An explicit `project_owners` table, if ownership ever needs to outlive all of a project's clients.
