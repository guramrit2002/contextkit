// GitHub sign-in by full-page redirect (ADR 030). sessionStorage holds only the OAuth state,
// a "reopen the key dialog" flag and the selected agent, and only until the user returns.

import { GITHUB_CLIENT_ID } from './api'

const STATE_KEY = 'ck_oauth_state'
const RETURN_KEY = 'ck_oauth_return'
const AGENT_KEY = 'ck_oauth_agent'
const RETURN_TO_DIALOG = 'get-key'

export type OAuthReturn =
  | { kind: 'none' }
  | { kind: 'code'; code: string; stateMatches: boolean; agentIndex: number }
  | { kind: 'cancelled'; agentIndex: number }

/** Must be the same string in the authorize URL, the backend call and the GitHub app. */
export function redirectUri(): string {
  return `${window.location.origin}/`
}

function randomState(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function storage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

/** Leave for GitHub's authorize page. No scope: the public profile is enough (ADR 028). */
export function beginGitHubSignIn(agentIndex: number): boolean {
  const session = storage()
  if (!session) return false
  const state = randomState()
  try {
    session.setItem(STATE_KEY, state)
    session.setItem(RETURN_KEY, RETURN_TO_DIALOG)
    session.setItem(AGENT_KEY, String(agentIndex))
  } catch {
    return false
  }
  const params = new URLSearchParams({
    client_id: GITHUB_CLIENT_ID,
    redirect_uri: redirectUri(),
    state,
    allow_signup: 'true',
  })
  window.location.assign(`https://github.com/login/oauth/authorize?${params}`)
  return true
}

function consume(): OAuthReturn {
  const url = new URL(window.location.href)
  const code = url.searchParams.get('code')
  const state = url.searchParams.get('state')
  const error = url.searchParams.get('error')
  if (!(code && state) && !error) return { kind: 'none' }

  // Single use: read, then forget, before anything else happens.
  const session = storage()
  const savedState = session?.getItem(STATE_KEY) ?? null
  const returnTo = session?.getItem(RETURN_KEY) ?? null
  const agentIndex = Number(session?.getItem(AGENT_KEY) ?? 0) || 0
  for (const key of [STATE_KEY, RETURN_KEY, AGENT_KEY]) session?.removeItem(key)

  // Strip GitHub's parameters before any network call, so the code never lingers in the
  // address bar or history, and Back can't replay the sign-in.
  for (const key of ['code', 'state', 'error', 'error_description', 'error_uri']) {
    url.searchParams.delete(key)
  }
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)

  if (returnTo !== RETURN_TO_DIALOG) return { kind: 'none' }
  if (error) return { kind: 'cancelled', agentIndex }
  return { kind: 'code', code: code ?? '', stateMatches: state === savedState, agentIndex }
}

let consumed: OAuthReturn | null = null

/** What GitHub sent the user back with, if anything. Safe to call more than once. */
export function takeOAuthReturn(): OAuthReturn {
  consumed ??= consume()
  return consumed
}
