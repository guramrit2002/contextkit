import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { GitHubRepo } from './api'

interface Props {
  /** null while loading. */
  repos: GitHubRepo[] | null
  /** Canonical project IDs that already have a key: shown, but not selectable. */
  keyed: Set<string>
  value: string
  onChange: (projectId: string) => void
  /** Labels the picker, e.g. the visible "Repository" label's id. */
  labelId: string
}

function updatedAgo(pushedAt: string | null): string | null {
  if (!pushedAt) return null
  const days = Math.floor((Date.now() - new Date(pushedAt).getTime()) / 86_400_000)
  if (Number.isNaN(days)) return null
  if (days < 1) return 'updated today'
  if (days === 1) return 'updated yesterday'
  if (days < 30) return `updated ${days} days ago`
  if (days < 365) return `updated ${Math.floor(days / 30)} mo ago`
  return `updated ${Math.floor(days / 365)} yr ago`
}

function Chevron() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="picker-chevron">
      <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** A searchable list of the user's repositories, in place of the browser's own dropdown. */
export default function RepoPicker({ repos, keyed, value, onChange, labelId }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const listId = useId()

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (repos ?? []).filter((repo) => repo.full_name.toLowerCase().includes(needle))
  }, [repos, query])
  const selected = repos?.find((repo) => repo.project_id === value) ?? null

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  useEffect(() => {
    list.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active, open])

  function openList() {
    if (!repos?.length) return
    setQuery('')
    const current = repos.findIndex((repo) => repo.project_id === value)
    setActive(Math.max(current, 0))
    setOpen(true)
  }

  function close(focusTrigger = true) {
    setOpen(false)
    if (focusTrigger) trigger.current?.focus()
  }

  function choose(repo: GitHubRepo | undefined) {
    if (!repo || keyed.has(repo.project_id)) return
    onChange(repo.project_id)
    close()
  }

  function onSearchKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(matches[active])
    } else if (event.key === 'Tab') {
      close(false)
    }
  }

  const loading = repos === null

  return (
    <div className="picker" ref={root}>
      <button
        ref={trigger}
        type="button"
        className={`picker-trigger ${selected ? '' : 'placeholder'}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={labelId}
        disabled={loading}
        onClick={() => (open ? close() : openList())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault()
            openList()
          }
        }}
        autoFocus
      >
        {loading && <span className="spinner small" aria-hidden="true" />}
        <span className="picker-value">
          {loading ? 'Loading your repositories…' : selected ? selected.full_name : 'Choose a repository'}
        </span>
        <Chevron />
      </button>

      {open && (
        <div
          className="picker-panel"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              // Close the list only: without this, the dialog would close too.
              event.preventDefault()
              event.stopPropagation()
              close()
            }
          }}
        >
          <input
            className="picker-search"
            type="search"
            placeholder="Search repositories"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={onSearchKey}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={matches[active] ? `${listId}-${active}` : undefined}
            aria-label="Search repositories"
            autoFocus
          />
          <ul
            id={listId}
            ref={list}
            className="picker-list"
            role="listbox"
            aria-labelledby={labelId}
            // Clicking an option must not take focus from the search box (keys keep working).
            onPointerDown={(event) => event.preventDefault()}
          >
            {matches.length === 0 && <li className="picker-empty">No repositories match.</li>}
            {matches.map((repo, index) => {
              const hasKey = keyed.has(repo.project_id)
              const [owner, name] = repo.full_name.split('/')
              const updated = updatedAgo(repo.pushed_at)
              return (
                <li
                  key={repo.project_id}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={repo.project_id === value}
                  aria-disabled={hasKey}
                  data-active={index === active}
                  className="picker-option"
                  onPointerMove={() => setActive(index)}
                  onClick={() => choose(repo)}
                >
                  <span className="picker-name">
                    <span className="picker-owner">{owner}/</span>
                    {name}
                  </span>
                  <span className="picker-meta">
                    {hasKey && <span className="pill keyed">has a key</span>}
                    {repo.fork && <span className="pill">fork</span>}
                    {updated && <span>{updated}</span>}
                  </span>
                  {repo.project_id === value && (
                    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="picker-check">
                      <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
