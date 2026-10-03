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

The dialog needs two public build-time values (see `.env.example`):

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | The Django backend that serves `/api/v1/`, no trailing slash |
| `VITE_GITHUB_CLIENT_ID` | Client ID of the GitHub OAuth app |

Without either one, the **Get key** button is hidden and the site is fully static: `dist/` can be
served by any static host or CDN.

When they are set:

- the GitHub OAuth app's callback URL must be this site's origin plus `/`;
- the backend needs `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` from the same app, and this
  site's origin in `DJANGO_CORS_ALLOWED_ORIGINS`.

The access token and any issued key live only in the page's memory and are dropped when the
dialog closes. `sessionStorage` holds only the OAuth state, a reopen flag and the selected agent,
and only until GitHub sends the user back.
