# ADR 028 — User API: JWT login and self-service API keys

**Status:** Accepted

**Implements:** the User API tier of ADR 024, with ADR 025's client naming

## Context

API keys (`ck_...`) could only be issued by an operator, with `manage.py create_client` or the Django admin. The platform needs users to get their own keys, from the website and later other clients, without admin access.

## Decision

Two endpoint groups under `/api/v1/`, served by Django:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/github/` | GitHub OAuth code → JWT access + refresh (how the website signs in) |
| `POST /api/v1/auth/token/` | Username + password → JWT access (15 min) + refresh (1 day), for admin-created accounts and scripts |
| `POST /api/v1/auth/token/refresh/` | Refresh → new access token |
| `GET /api/v1/clients/` | The caller's clients (never the key or its hash) |
| `POST /api/v1/clients/` | Create a client for a project; returns the key **once** |
| `GET /api/v1/clients/{id}/` | One of the caller's clients |
| `POST /api/v1/clients/{id}/rotate/` | New key, returned once; the old key stops working |
| `DELETE /api/v1/clients/{id}/` | Revoke: deletes the client and its key |

- **Auth:** JWT (`djangorestframework-simplejwt`) in the `Authorization: Bearer` header. Session cookies and API keys are not accepted on these endpoints, so there is no CSRF surface and an API key can never manage keys.
- **GitHub sign-in:** the website sends the user to GitHub's OAuth authorize page with a random `state`; GitHub redirects back to the website with a one-time `code`, which the website posts to `/api/v1/auth/github/`. Django exchanges it with the client secret (which never leaves the server), reads the GitHub user, and links or creates a Django user by GitHub's **numeric id** (logins can be renamed). Our JWT is returned in the response body, never in a URL. No OAuth scopes are requested, only the public profile. GitHub-created users have no usable password. An optional `GITHUB_ALLOWED_LOGINS` allowlist restricts who can sign in; empty means any GitHub user.
- **Ownership:** a client's `user_id` is the Django user's id. Users see and change only their own clients; anyone else's returns 404, as if it did not exist.
- **Keys:** plaintext only in create and rotate responses (`Cache-Control: no-store`); only the SHA-256 hash is stored (ADR 022).
- **Brute force:** login and refresh are throttled per client IP (`DJANGO_AUTH_THROTTLE_RATE`, default `10/min`).
- **Browser access:** CORS (`django-cors-headers`) only on `/api/v1/`, only for origins in `DJANGO_CORS_ALLOWED_ORIGINS`, and without credentials. The agent REST API and the admin never send CORS headers.
- Logic lives in `clients/services.py` (CLAUDE.md rule 6); views only validate and shape responses.

## Consequences

- The website can log a user in and hand them a key in one flow.
- Any registered user can create a client for any project ID; there is no project ownership model yet (per-user keys and project normalization are deferred in ADR 026).
- The throttle uses Django's default in-process cache, so the limit applies per worker process. A shared cache (e.g. Redis) would make it global.
- Access tokens live 15 minutes and are not revocable before expiry; refresh tokens are not blacklisted on logout.

## Deferred

- Password reset for admin-created accounts (GitHub users need none).
- Refresh-token blacklisting and logout.
- A shared cache for throttling across workers.
