import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

/** Shown last: lets the user type a name that isn't in the list. */
export const NEW_NAME = '__new_name__'

interface Props {
  /** The agents to offer, e.g. Claude Code, Codex. */
  options: string[]
  /** The chosen agent, or NEW_NAME for a typed name. */
  value: string
  onChange: (value: string) => void
  labelId: string
}

function Chevron() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="picker-chevron">
      <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Which agent a key is for, in place of the browser's own dropdown. */
export default function ClientPicker({ options, value, onChange, labelId }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const listId = useId()
  const items = [...options, NEW_NAME]

  useEffect(() => {
    if (!open) return
    list.current?.focus()
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  function openList() {
    setActive(Math.max(items.indexOf(value), 0))
    setOpen(true)
  }

  function close() {
    setOpen(false)
    trigger.current?.focus()
  }

  function choose(item: string) {
    onChange(item)
    close()
  }

  function onListKey(event: KeyboardEvent<HTMLUListElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, items.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      choose(items[active])
    } else if (event.key === 'Escape') {
      // Close the list only, not the whole dialog.
      event.preventDefault()
      event.stopPropagation()
      close()
    } else if (event.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div className="picker" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="picker-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={labelId}
        onClick={() => (open ? close() : openList())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault()
            openList()
          }
        }}
      >
        <span className="picker-value">{value === NEW_NAME ? 'Add a new name…' : value}</span>
        <Chevron />
      </button>

      {open && (
        <div className="picker-panel">
          <ul
            id={listId}
            ref={list}
            className="picker-list short"
            role="listbox"
            tabIndex={-1}
            aria-labelledby={labelId}
            aria-activedescendant={`${listId}-${active}`}
            onKeyDown={onListKey}
            onPointerDown={(event) => event.preventDefault()}
          >
            {items.map((item, index) => (
              <li
                key={item}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={item === value}
                data-active={index === active}
                className={`picker-option single ${item === NEW_NAME ? 'new-name' : ''}`}
                onPointerMove={() => setActive(index)}
                onClick={() => choose(item)}
              >
                <span className="picker-name">{item === NEW_NAME ? 'Add a new name…' : item}</span>
                {item === value && (
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="picker-check">
                    <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
