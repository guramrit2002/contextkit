// Calls to the contextkit user API (ADR 028). The JWT is only ever held in memory.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export interface IssuedKey {
  id: string
  name: string
  project_id: string
  api_key: string
}

export class ApiError extends Error {}

export function isConfigured(): boolean {
  return BASE_URL.length > 0
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

async function post<T>(path: string, body: object, token?: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError("Can't reach the contextkit backend. Try again in a moment.")
  }

  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T

  if (response.status === 429) {
    throw new ApiError('Too many attempts. Wait a minute and try again.')
  }
  throw new ApiError(firstMessage(data) ?? `Request failed (${response.status}).`)
}

export async function logIn(username: string, password: string): Promise<string> {
  try {
    const tokens = await post<{ access: string }>('/api/v1/auth/token/', { username, password })
    return tokens.access
  } catch (error) {
    if (error instanceof ApiError && error.message.startsWith('No active account')) {
      throw new ApiError('Wrong username or password.')
    }
    throw error
  }
}

export function createKey(token: string, projectId: string, name: string): Promise<IssuedKey> {
  return post<IssuedKey>('/api/v1/clients/', { project_id: projectId, name }, token)
}
