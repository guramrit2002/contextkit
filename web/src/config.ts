// The website's two public settings, read at runtime from /config.json (ADR 030, spec Part 3)
// so a new backend URL (the quick tunnel restarts) needs a file edit, not a rebuild.
// Precedence per field: a valid value in config.json, then the build-time VITE_* variable.

const CONFIG_PATH = '/config.json'
const TIMEOUT_MS = 3000
const LOCAL_HOSTS = ['localhost', '127.0.0.1']
const CLIENT_ID_PATTERN = /^[A-Za-z0-9._-]{1,100}$/

interface Settings {
  apiBaseUrl: string
  githubClientId: string
}

function trimSlashes(url: string): string {
  return url.trim().replace(/\/+$/, '')
}

const buildTime: Settings = {
  apiBaseUrl: trimSlashes(import.meta.env.VITE_API_BASE_URL ?? ''),
  githubClientId: (import.meta.env.VITE_GITHUB_CLIENT_ID ?? '').trim(),
}

let loaded: Partial<Settings> = {}

/** https only, except http on this machine for local development. */
function validApiBaseUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value.trim())
    const local = url.protocol === 'http:' && LOCAL_HOSTS.includes(url.hostname)
    return url.protocol === 'https:' || local ? trimSlashes(url.href) : null
  } catch {
    return null
  }
}

function validClientId(value: unknown): string | null {
  return typeof value === 'string' && CLIENT_ID_PATTERN.test(value.trim()) ? value.trim() : null
}

function read(body: unknown): Partial<Settings> {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    console.warn('config.json is not a JSON object; using build-time settings.')
    return {}
  }
  const record = body as Record<string, unknown>
  const settings: Partial<Settings> = {}
  if ('apiBaseUrl' in record) {
    const url = validApiBaseUrl(record.apiBaseUrl)
    if (url) settings.apiBaseUrl = url
    else console.warn('config.json: ignoring apiBaseUrl (must be an https URL):', record.apiBaseUrl)
  }
  if ('githubClientId' in record) {
    const id = validClientId(record.githubClientId)
    if (id) settings.githubClientId = id
    else console.warn('config.json: ignoring githubClientId (unexpected format):', record.githubClientId)
  }
  return settings
}

/**
 * Fetch /config.json from this site's own origin, once. Never rejects: a missing file, bad JSON,
 * a network error or the 3-second timeout all leave the build-time settings in place.
 */
export async function loadConfig(): Promise<void> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    // A fixed relative path: config never comes from another origin or a URL parameter, so a
    // crafted link can't point the dialog at someone else's backend.
    const response = await fetch(CONFIG_PATH, { cache: 'no-store', signal: controller.signal })
    if (!response.ok) return
    loaded = read(await response.json())
  } catch (error) {
    if (error instanceof SyntaxError) {
      console.warn('config.json is not valid JSON; using build-time settings.')
    }
    // Missing, unreachable or slow: build-time settings apply.
  } finally {
    window.clearTimeout(timer)
  }
}

export function apiBaseUrl(): string {
  return loaded.apiBaseUrl ?? buildTime.apiBaseUrl
}

export function githubClientId(): string {
  return loaded.githubClientId ?? buildTime.githubClientId
}
