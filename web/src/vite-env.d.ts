/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the contextkit Django backend that serves /api/v1/, e.g. https://api.example.com */
  readonly VITE_API_BASE_URL?: string
  /** Client ID of the GitHub OAuth app whose callback URL is this site's origin plus "/". */
  readonly VITE_GITHUB_CLIENT_ID?: string
  /** Local development only: the backend's GitHub mock page instead of github.com. */
  readonly VITE_GITHUB_AUTHORIZE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
