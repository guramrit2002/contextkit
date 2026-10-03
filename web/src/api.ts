// Calls to the contextkit user API (ADR 028, ADR 030). The JWT is only ever held in memory.

import { apiBaseUrl, githubClientId } from './config'

export interface ClientKey {
  id: string
  name: string
  project_id: string
  created_at: string
}

export interface IssuedKey extends ClientKey {
  api_key: string
}

export interface GitHubRepo {
  full_name: string
  /** The canonical project ID a key for this repository is stored under. */
  project_id: string
  pushed_at: string | null
  fork: boolean
}

export class ApiError extends Error {
  readonly status: number | null
  /** The first error per request field from a 400 (e.g. project_id, name), for inline display. */
  readonly fields: Record<string, string>

  constructor(message: string, status: number | null = null, fields: Record<string, string> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }

  /** The JWT was rejected: the user has to sign in again. */
  get signedOut(): boolean {
    return this.status === 401
  }
}

/** Both values are needed for the Get key flow; without them the site stays fully static. */
export function isConfigured(): boolean {
  return apiBaseUrl().length > 0 && githubClientId().length > 0
}

function firstMessage(body: unknown): string | null {
  if (typeof body === 'string') return body
  if (Array.isArray(body)) return firstMessage(body[0])
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    if ('detail' in record) return firstMessage(record.detail)
    for (const value of Object.values(record)) {
      const message = firstMessage(value)
      if (message) return message
    }
  }
  return null
}

function fieldMessages(body: unknown): Record<string, string> {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return {}
  const fields: Record<string, string> = {}
  for (const [field, value] of Object.entries(body as Record<string, unknown>)) {
    const message = field === 'detail' ? null : firstMessage(value)
    if (message) fields[field] = message
  }
  return fields
}

async function request<T>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  options: { body?: object; token?: string } = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError("Can't reach the contextkit backend. Try again in a moment.")
  }

  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T

  if (response.status === 429) {
    throw new ApiError('Too many attempts. Wait a minute and try again.', 429)
  }
  if (response.status === 401 && options.token) {
    throw new ApiError('Your sign-in expired. Please sign in again.', 401)
  }
  throw new ApiError(
    firstMessage(data) ?? `Request failed (${response.status}).`,
    response.status,
    fieldMessages(data),
  )
}

/** Exchange a GitHub OAuth code for a contextkit access token. The refresh token is unused. */
export async function signInWithGitHub(code: string, redirectUri: string): Promise<string> {
  try {
    const tokens = await request<{ access: string }>('POST', '/api/v1/auth/github/', {
      body: { code, redirect_uri: redirectUri },
    })
    return tokens.access
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      throw new ApiError("This GitHub account isn't allowed to sign in.", 403)
    }
    if (error instanceof ApiError && error.status === 503) {
      throw new ApiError("GitHub sign-in isn't set up on the server.", 503)
    }
    throw error
  }
}

export function listKeys(token: string): Promise<ClientKey[]> {
  return request<ClientKey[]>('GET', '/api/v1/clients/', { token })
}

/** The user's public GitHub repositories, most recently pushed first (no extra scope). */
export async function listGitHubRepos(token: string): Promise<GitHubRepo[]> {
  const body = await request<{ repositories: GitHubRepo[] }>('GET', '/api/v1/github/repos/', {
    token,
  })
  return body.repositories
}

export function createKey(token: string, projectUrl: string, name: string): Promise<IssuedKey> {
  return request<IssuedKey>('POST', '/api/v1/clients/', {
    body: { project_id: projectUrl, name },
    token,
  })
}

export function rotateKey(token: string, id: string): Promise<IssuedKey> {
  return request<IssuedKey>('POST', `/api/v1/clients/${encodeURIComponent(id)}/rotate/`, {
    token,
  })
}

export async function revokeKey(token: string, id: string): Promise<void> {
  await request<null>('DELETE', `/api/v1/clients/${encodeURIComponent(id)}/`, { token })
}
