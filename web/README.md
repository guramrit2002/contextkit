# contextkit website

Single-section landing page for contextkit (React + TypeScript, built with Vite). The "API key"
button signs a user in and issues a key through the backend's user API (ADR 028).

```bash
npm install
cp .env.example .env.local   # set VITE_API_BASE_URL to the Django backend
npm run dev                  # http://localhost:5173
npm run lint
npm run build                # static files in dist/
```

The backend must allow this site's origin: add it to `DJANGO_CORS_ALLOWED_ORIGINS`
(for local development, `http://localhost:5173`). `VITE_API_BASE_URL` is compiled into the
bundle at build time, so set it before `npm run build`.
