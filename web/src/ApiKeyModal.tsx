import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  createKey,
  listGitHubRepos,
  listKeys,
  revokeKey,
  rotateKey,
  signInWithGitHub,
  type ClientKey,
  type GitHubRepo,
  type IssuedKey,
} from './api'
import { beginGitHubSignIn, redirectUri, type OAuthReturn } from './oauth'
import RepoPicker from './RepoPicker'
import { setupWithKey, type AgentSetup } from './setups'

type Step = 'signin' | 'signing-in' | 'keys' | 'create' | 'issued'

const EXPIRED_STATE = 'Sign-in expired or was interrupted. Please try again.'
const CANCELLED = 'GitHub sign-in was cancelled.'

interface Props {
  open: boolean
  onClose: () => void
  /** The agent selected on the page: names new keys and picks the connect text. */
  setup: AgentSetup
  agentIndex: number
  /** What GitHub sent the user back with when the page loaded. */
  oauthReturn: OAuthReturn
}

interface PendingAction {
  id: string
  kind: 'rotate' | 'revoke'
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Try again.'
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button type="button" className="copy" onClick={copy} aria-label={label}>
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

/** Only a code whose state matches what this browser sent is exchanged for a token. */
function hasValidCode(oauthReturn: OAuthReturn): boolean {
  return oauthReturn.kind === 'code' && oauthReturn.stateMatches
}

function initialError(oauthReturn: OAuthReturn): string | null {
  if (oauthReturn.kind === 'cancelled') return CANCELLED
  if (oauthReturn.kind === 'code' && !oauthReturn.stateMatches) return EXPIRED_STATE
  return null
}

export default function ApiKeyModal({ open, onClose, setup, agentIndex, oauthReturn }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const exchanged = useRef(false)
  const [step, setStep] = useState<Step>(() =>
    hasValidCode(oauthReturn) ? 'signing-in' : 'signin',
  )
  const [token, setToken] = useState<string | null>(null)
  const [keys, setKeys] = useState<ClientKey[]>([])
  const [issued, setIssued] = useState<IssuedKey | null>(null)
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [error, setError] = useState<string | null>(() => initialError(oauthReturn))
  const [busy, setBusy] = useState(false)
  // The repository picker: null until loaded; a typed URL is always available as a fallback.
  const [repos, setRepos] = useState<GitHubRepo[] | null>(null)
  const [reposError, setReposError] = useState<string | null>(null)
  const [typeUrl, setTypeUrl] = useState(false)
  const [pickedRepo, setPickedRepo] = useState('')
  const reposRequested = useRef(false)

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  }, [open])

  function fail(caught: unknown) {
    if (caught instanceof ApiError && caught.signedOut) {
      // Drop the rejected token and everything loaded with it.
      setToken(null)
      setKeys([])
      setIssued(null)
      setPending(null)
      setRepos(null)
      reposRequested.current = false
      setStep('signin')
    }
    setError(errorMessage(caught))
  }

  async function showKeys(accessToken: string) {
    const list = await listKeys(accessToken)
    setKeys(list)
    setStep(list.length === 0 ? 'create' : 'keys')
  }

  useEffect(() => {
    // Exchange GitHub's code once, even when React runs effects twice in development.
    if (oauthReturn.kind !== 'code' || !oauthReturn.stateMatches || exchanged.current) return
    exchanged.current = true
    void (async () => {
      try {
        const accessToken = await signInWithGitHub(oauthReturn.code, redirectUri())
        setToken(accessToken)
        await showKeys(accessToken)
      } catch (caught) {
        setStep('signin')
        setError(errorMessage(caught))
      }
    })()
  }, [oauthReturn])

  useEffect(() => {
    // Load once per sign-in, the first time the create form is shown.
    if (step !== 'create' || !token || reposRequested.current) return
    reposRequested.current = true
    listGitHubRepos(token).then(setRepos, (caught: unknown) => {
      if (caught instanceof ApiError && caught.signedOut) fail(caught)
      else setReposError(errorMessage(caught))
    })
  }, [step, token])

  function reset() {
    // Forget the session, the key list and any issued key when the dialog closes.
    setStep('signin')
    setToken(null)
    setKeys([])
    setIssued(null)
    setPending(null)
    setError(null)
    setBusy(false)
    setRepos(null)
    setReposError(null)
    setTypeUrl(false)
    setPickedRepo('')
    reposRequested.current = false
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (caught) {
      fail(caught)
    } finally {
      setBusy(false)
    }
  }

  function continueWithGitHub() {
    setError(null)
    if (!beginGitHubSignIn(agentIndex)) {
      setError('Sign-in needs browser storage. Allow it for this site and try again.')
    }
  }

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token) return
    const form = new FormData(event.currentTarget)
    const repository = String(form.get('repository') ?? '').trim()
    if (!repository) {
      setError('Choose a repository, or use a different URL.')
      return
    }
    void run(async () => {
      setIssued(await createKey(token, repository, String(form.get('name'))))
      setPickedRepo('')
      setStep('issued')
    })
  }

  function confirmPending() {
    if (!token || !pending) return
    const { id, kind } = pending
    void run(async () => {
      if (kind === 'rotate') {
        setIssued(await rotateKey(token, id))
        setStep('issued')
      } else {
        await revokeKey(token, id)
        await showKeys(token)
      }
      setPending(null)
    })
  }

  function finishIssued() {
    setIssued(null)
    if (token) void run(() => showKeys(token))
  }

  // The picker shows while loading and once there are repositories, unless the user chose to type.
  const showPicker = !typeUrl && !reposError && (repos === null || repos.length > 0)
  const keyedProjects = new Set(keys.map((key) => key.project_id))

  const title = step === 'issued' ? 'Your API key' : step === 'keys' ? 'Your API keys' : 'Get an API key'
  const connectText = issued ? setupWithKey(setup, issued.api_key) : ''

  return (
    <dialog ref={dialog} className="modal" onClose={handleClose} aria-labelledby="modal-title">
      <div className="modal-head">
        <h2 id="modal-title">{title}</h2>
        <button type="button" className="modal-close" onClick={handleClose} aria-label="Close">
          ×
        </button>
      </div>

      {step === 'signin' && (
        <div className="form">
          <p className="form-intro">Authenticate yourself using GitHub.</p>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="button" className="button primary" onClick={continueWithGitHub}>
            Continue with GitHub
          </button>
        </div>
      )}

      {step === 'signing-in' && (
        <div className="form signing-in" role="status">
          <span className="spinner" aria-hidden="true" />
          Signing you in…
        </div>
      )}

      {step === 'keys' && (
        <div className="form">
          <ul className="key-list">
            {keys.map((key) => (
              <li key={key.id} className="key-item">
                <div className="key-meta">
                  <strong>{key.name}</strong>
                  <span className="key-project">{key.project_id}</span>
                  <span className="key-date">Created {formatDate(key.created_at)}</span>
                </div>
                {pending?.id === key.id ? (
                  <div className="key-confirm">
                    <p>
                      {pending.kind === 'rotate'
                        ? 'Agents using the old key will stop working.'
                        : 'This key stops working immediately.'}
                    </p>
                    <div className="key-actions">
                      <button
                        type="button"
                        className="button small danger"
                        onClick={confirmPending}
                        disabled={busy}
                      >
                        {pending.kind === 'rotate' ? 'Rotate key' : 'Revoke key'}
                      </button>
                      <button
                        type="button"
                        className="button small"
                        onClick={() => setPending(null)}
                        disabled={busy}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="key-actions">
                    <button
                      type="button"
                      className="button small"
                      onClick={() => setPending({ id: key.id, kind: 'rotate' })}
                      disabled={busy}
                    >
                      Rotate
                    </button>
                    <button
                      type="button"
                      className="button small"
                      onClick={() => setPending({ id: key.id, kind: 'revoke' })}
                      disabled={busy}
                    >
                      Revoke
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button
            type="button"
            className="button primary"
            onClick={() => {
              setError(null)
              setPending(null)
              setStep('create')
            }}
            disabled={busy}
          >
            New key
          </button>
        </div>
      )}

      {step === 'create' && (
        <form className="form" onSubmit={submitCreate}>
          <p className="form-intro">A key works for one repository.</p>
          {showPicker ? (
            <div className="field">
              <span className="field-label" id="repository-label">
                Repository
              </span>
              <RepoPicker
                repos={repos}
                keyed={keyedProjects}
                value={pickedRepo}
                onChange={(projectId) => {
                  setPickedRepo(projectId)
                  setError(null)
                }}
                labelId="repository-label"
              />
              <input type="hidden" name="repository" value={pickedRepo} />
            </div>
          ) : (
            <label>
              Repository URL
              <input
                name="repository"
                placeholder="https://github.com/you/repo"
                maxLength={500}
                required
                autoFocus
              />
            </label>
          )}
          <p className="field-hint">
            {showPicker
              ? 'Only your public repositories are listed. '
              : reposError
                ? `${reposError} Enter the URL instead. `
                : repos?.length === 0
                  ? 'No public repositories found. Enter the URL instead. '
                  : 'Any form works: https, SSH, with or without .git. '}
            {!reposError && (repos === null || repos.length > 0) && (
              <button type="button" className="link-button" onClick={() => setTypeUrl(!typeUrl)}>
                {typeUrl ? 'Choose from your repositories' : 'Use a different URL'}
              </button>
            )}
          </p>
          <label>
            Key name
            <input name="name" defaultValue={setup.agent} maxLength={255} required />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create key'}
          </button>
          {keys.length > 0 && (
            <button
              type="button"
              className="button"
              onClick={() => {
                setError(null)
                setStep('keys')
              }}
              disabled={busy}
            >
              Back to your keys
            </button>
          )}
        </form>
      )}

      {step === 'issued' && issued && (
        <div className="form">
          <p className="form-warning" role="status">
            Save it now. It won't be shown again.
          </p>
          <span className="field-label">API key for {issued.project_id}</span>
          <div className="command">
            <code data-testid="issued-key">{issued.api_key}</code>
            <CopyButton text={issued.api_key} label="Copy API key" />
          </div>
          <span className="field-label">
            {setup.kind === 'command'
              ? `Connect ${setup.agent}: run in your terminal`
              : `Connect ${setup.agent}: add to ${setup.file}`}
          </span>
          <div className={`command ${setup.kind === 'config' ? 'multiline' : ''}`}>
            <code>{connectText}</code>
            <CopyButton text={connectText} label={`Copy ${setup.agent} setup`} />
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="button" className="button primary" onClick={finishIssued} disabled={busy}>
            Done
          </button>
        </div>
      )}
    </dialog>
  )
}
