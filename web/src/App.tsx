import { useEffect, useState } from 'react'
import ApiKeyModal from './ApiKeyModal'
import { isConfigured } from './api'
import { takeOAuthReturn } from './oauth'
import { SETUPS } from './setups'
import ThemeToggle from './ThemeToggle'

const REPO_URL = 'https://github.com/guramrit2002/contextkit'
// HEAD resolves to the default branch on GitHub.
const GUIDES_URL = `${REPO_URL}/blob/HEAD/docs/guide`

const FEATURES = [
  'API-key auth on every call',
  'One project per key',
  'Secrets redacted before storage',
  'Every call audited',
]

interface ConnectCommandProps {
  selected: number
  onSelect: (index: number) => void
}

function ConnectCommand({ selected, onSelect }: ConnectCommandProps) {
  const [copied, setCopied] = useState(false)
  const setup = SETUPS[selected]

  async function copy() {
    try {
      await navigator.clipboard.writeText(setup.text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="setup">
      <div className="setup-tab">
        <label className="sr-only" htmlFor="setup-agent">
          Your agent
        </label>
        <select
          id="setup-agent"
          value={selected}
          onChange={(event) => {
            onSelect(Number(event.target.value))
            setCopied(false)
          }}
        >
          {SETUPS.map((option, index) => (
            <option key={option.agent} value={index}>
              {option.agent}
            </option>
          ))}
        </select>
        <span className="setup-hint">
          {setup.kind === 'command' ? 'Run in your terminal' : `Add to ${setup.file}`}
        </span>
      </div>
      <div className={`command ${setup.kind === 'config' ? 'multiline' : ''}`}>
        <code data-testid="setup-text">
          {setup.kind === 'command' && (
            <span className="prompt" aria-hidden="true">
              $
            </span>
          )}
          {setup.text}
        </code>
        <button type="button" onClick={copy} className="copy">
          {copied ? 'Copied' : 'Copy'}
        </button>
        <span className="sr-only" aria-live="polite">
          {copied ? `${setup.agent} setup copied to clipboard` : ''}
        </span>
      </div>
    </div>
  )
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" width="24" height="24" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

// MCP-capable coding agents the eyebrow and the diagram cycle through.
const AGENTS = ['Claude Code', 'Codex', 'Cursor', 'Windsurf', 'Gemini CLI', 'GitHub Copilot', 'Cline']
const AGENT_INTERVAL_MS = 2600
// The receiving agent is always a different one: the diagram shows a handoff.
const HANDOFF_OFFSET = 2

/** One shared counter, so the eyebrow and the diagram always change together. */
function useAgentStep(): number {
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timer = window.setInterval(() => setStep((current) => current + 1), AGENT_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [])

  return step
}

function agentAt(step: number): string {
  return AGENTS[step % AGENTS.length]
}

function RotatingName({ name }: { name: string }) {
  // A new key restarts the fade-in for each name.
  return (
    <span key={name} className="agent-swap">
      {name}
    </span>
  )
}

function HandoffDiagram({ step }: { step: number }) {
  const from = agentAt(step)
  const to = agentAt(step + HANDOFF_OFFSET)

  return (
    <figure className="handoff" aria-label="An agent hands off work through contextkit">
      <div className="agent">
        <span className="agent-name">
          <RotatingName name={from} />
        </span>
        <span className="call">log_session</span>
        <p>Added JWT login, rotation still to do.</p>
      </div>

      <div className="link" aria-hidden="true" />

      <div className="store">
        <span className="store-name">contextkit</span>
        <ul>
          <li>
            <strong>12</strong> decisions
          </li>
          <li>
            <strong>1</strong> current state
          </li>
          <li>
            <strong>8</strong> sessions
          </li>
        </ul>
      </div>

      <div className="link" aria-hidden="true" />

      <div className="agent">
        <span className="agent-name">
          <RotatingName name={to} />
        </span>
        <span className="call">get_context</span>
        <p>Picks up at key rotation, with every decision behind it.</p>
      </div>
    </figure>
  )
}

function validAgentIndex(index: number): number {
  return Number.isInteger(index) && index >= 0 && index < SETUPS.length ? index : 0
}

export default function App() {
  const step = useAgentStep()
  // Read once: GitHub's code and state are stripped from the address bar as they are read.
  const [oauthReturn] = useState(takeOAuthReturn)
  const [selected, setSelected] = useState(() =>
    oauthReturn.kind === 'none' ? 0 : validAgentIndex(oauthReturn.agentIndex),
  )
  const [keyDialogOpen, setKeyDialogOpen] = useState(
    () => isConfigured() && oauthReturn.kind !== 'none',
  )
  const setup = SETUPS[selected]

  return (
    <main className="hero">
      <header className="bar">
        <a className="brand" href="/" aria-label="contextkit home">
          <img src="/favicon.svg" alt="" width="28" height="28" />
          contextkit
        </a>
        <div className="bar-actions">
          {isConfigured() && (
            <button
              type="button"
              className="button small"
              onClick={() => setKeyDialogOpen(true)}
            >
              Get key
            </button>
          )}
          <ThemeToggle />
          <a className="bar-icon" href={REPO_URL} aria-label="contextkit on GitHub" title="GitHub">
            <GitHubMark />
          </a>
        </div>
      </header>

      <section className="content">
        <div className="copy-block">
          <p className="eyebrow">
            MCP server for developers for smoother handoffs between coding agents.
          </p>
          <h1>
            Switch AI agents.
            <br />
            Keep the context.
          </h1>
          <p className="lede">
            contextkit stores your project's decisions, progress and session history. The next
            coding agent loads it with one call and continues where the last one stopped, with no
            handoff doc to write.
          </p>

          <ConnectCommand selected={selected} onSelect={setSelected} />

          <div className="actions">
            <a className="button primary" href={`${GUIDES_URL}/${setup.guide}.md`}>
              {setup.agent} setup guide
            </a>
          </div>

          <ul className="features">
            {FEATURES.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </div>

        <HandoffDiagram step={step} />
      </section>

      {isConfigured() && (
        <ApiKeyModal
          open={keyDialogOpen}
          onClose={() => setKeyDialogOpen(false)}
          setup={setup}
          agentIndex={selected}
          oauthReturn={oauthReturn}
        />
      )}
    </main>
  )
}
