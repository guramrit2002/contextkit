import { useState } from 'react'
import ApiKeyModal from './ApiKeyModal'

const REPO_URL = 'https://github.com/guramrit2002/contextkit'
const CONNECT_COMMAND =
  'claude mcp add --transport http contextkit https://contextkit.onrender.com/mcp --header "Authorization: Bearer ck_..."'

const FEATURES = [
  'API-key auth on every call',
  'One project per key',
  'Secrets redacted before storage',
  'Every call audited',
]

function CopyCommand() {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(CONNECT_COMMAND)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="command">
      <code>
        <span className="prompt" aria-hidden="true">$</span>
        {CONNECT_COMMAND}
      </code>
      <button type="button" onClick={copy} className="copy">
        {copied ? 'Copied' : 'Copy'}
      </button>
      <span className="sr-only" aria-live="polite">
        {copied ? 'Command copied to clipboard' : ''}
      </span>
    </div>
  )
}

function HandoffDiagram() {
  return (
    <figure className="handoff" aria-label="An agent hands off work through contextkit">
      <div className="agent">
        <span className="agent-name">Claude Code</span>
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
        <span className="agent-name">Cursor</span>
        <span className="call">get_context</span>
        <p>Picks up at key rotation, with every decision behind it.</p>
      </div>
    </figure>
  )
}

export default function App() {
  const [keyOpen, setKeyOpen] = useState(false)

  return (
    <main className="hero">
      <header className="bar">
        <a className="brand" href="/" aria-label="contextkit home">
          <img src="/favicon.svg" alt="" width="28" height="28" />
          contextkit
        </a>
        <button type="button" className="button primary small" onClick={() => setKeyOpen(true)}>
          API key
        </button>
      </header>

      <section className="content">
        <div className="copy-block">
          <p className="eyebrow">MCP server for Claude Code, Codex and Cursor</p>
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

          <CopyCommand />

          <div className="actions">
            <a className="button primary" href={REPO_URL}>
              View on GitHub
            </a>
            <a className="button" href={`${REPO_URL}#hosted-no-install`}>
              Setup guide
            </a>
          </div>

          <ul className="features">
            {FEATURES.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </div>

        <HandoffDiagram />
      </section>

      <ApiKeyModal open={keyOpen} onClose={() => setKeyOpen(false)} />
    </main>
  )
}
