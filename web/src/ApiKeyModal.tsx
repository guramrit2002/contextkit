import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, createKey, isConfigured, logIn, type IssuedKey } from './api'

const MCP_URL = 'https://contextkit.onrender.com/mcp'

type Step = 'login' | 'create' | 'done'

interface Props {
  open: boolean
  onClose: () => void
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Try again.'
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

export default function ApiKeyModal({ open, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [step, setStep] = useState<Step>('login')
  const [token, setToken] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedKey | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open && !element.open) element.showModal()
    if (!open && element.open) element.close()
  }, [open])

  function reset() {
    // Forget the session and the key when the dialog closes.
    setStep('login')
    setToken(null)
    setIssued(null)
    setError(null)
    setBusy(false)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError(null)
    try {
      setToken(await logIn(String(form.get('username')), String(form.get('password'))))
      setStep('create')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError(null)
    try {
      setIssued(await createKey(token, String(form.get('project_id')), String(form.get('name'))))
      setStep('done')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  const command = issued
    ? `claude mcp add --transport http contextkit ${MCP_URL} --header "Authorization: Bearer ${issued.api_key}"`
    : ''

  return (
    <dialog ref={dialog} className="modal" onClose={handleClose} aria-labelledby="modal-title">
      <div className="modal-head">
        <h2 id="modal-title">
          {step === 'done' ? 'Your API key' : 'Get an API key'}
        </h2>
        <button type="button" className="modal-close" onClick={handleClose} aria-label="Close">
          ×
        </button>
      </div>

      {!isConfigured() && (
        <p className="form-error" role="alert">
          This site isn't connected to a contextkit backend (VITE_API_BASE_URL is not set).
        </p>
      )}

      {step === 'login' && (
        <form className="form" onSubmit={submitLogin}>
          <p className="form-intro">Sign in with your contextkit account.</p>
          <label>
            Username
            <input name="username" autoComplete="username" required autoFocus />
          </label>
          <label>
            Password
            <input name="password" type="password" autoComplete="current-password" required />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button primary" disabled={busy || !isConfigured()}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      )}

      {step === 'create' && (
        <form className="form" onSubmit={submitCreate}>
          <p className="form-intro">
            A key works for one project. Use the project's git remote URL, exactly as your agent
            sees it.
          </p>
          <label>
            Project
            <input
              name="project_id"
              placeholder="https://github.com/you/repo.git"
              maxLength={500}
              required
              autoFocus
            />
          </label>
          <label>
            Key name
            <input name="name" placeholder="laptop" maxLength={255} required />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create key'}
          </button>
        </form>
      )}

      {step === 'done' && issued && (
        <div className="form">
          <p className="form-warning" role="status">
            Copy this key now. It is shown only once and can't be recovered.
          </p>
          <span className="field-label">API key for {issued.project_id}</span>
          <div className="command">
            <code data-testid="issued-key">{issued.api_key}</code>
            <CopyButton text={issued.api_key} label="Copy API key" />
          </div>
          <span className="field-label">Connect Claude Code</span>
          <div className="command">
            <code>{command}</code>
            <CopyButton text={command} label="Copy connect command" />
          </div>
          <button type="button" className="button" onClick={handleClose}>
            Done
          </button>
        </div>
      )}
    </dialog>
  )
}
