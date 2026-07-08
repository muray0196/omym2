"use client"

import {
  Check,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  Music,
  Route as RouteIcon,
  Search,
  Settings,
  ShieldCheck,
  SquareTerminal,
  type LucideIcon,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useApp, type Route } from "./app-context"
import { CommandRow, Keycap } from "./command-kit"
import { cn, formatTimestamp, truncateMiddle } from "./lib"
import { toneForStatus, type Tone } from "./primitives"

interface PaletteItem {
  id: string
  group: "Navigate" | "Runs" | "CLI commands"
  label: string
  keywords: string
  icon: LucideIcon
  hint?: string
  tone?: Tone
  action: () => void | "copied"
}

const NAV_ENTRIES: { label: string; icon: LucideIcon; route: Route; keywords: string }[] = [
  {
    label: "Dashboard",
    icon: LayoutDashboard,
    route: { name: "dashboard" },
    keywords: "home overview",
  },
  {
    label: "Settings",
    icon: Settings,
    route: { name: "settings" },
    keywords: "config configuration",
  },
  {
    label: "Path Policy",
    icon: RouteIcon,
    route: { name: "path-policy" },
    keywords: "template preview canonical",
  },
  {
    label: "Plans",
    icon: ClipboardList,
    route: { name: "plans" },
    keywords: "review target paths",
  },
  { label: "Runs", icon: ListChecks, route: { name: "runs" }, keywords: "history apply" },
  {
    label: "Check",
    icon: ShieldCheck,
    route: { name: "check" },
    keywords: "issues consistency diagnostics",
  },
  { label: "Tracks", icon: Music, route: { name: "tracks" }, keywords: "library files music" },
]

const CLI_ENTRIES: { command: string; description: string }[] = [
  { command: "omym2 check", description: "Run consistency diagnostics" },
  { command: "omym2 organize", description: "Re-plan canonical placement" },
  { command: "omym2 add <path>", description: "Add incoming files" },
  { command: "omym2 refresh <library-file>", description: "Refresh DB state for a file" },
  { command: "omym2 history", description: "Review runs and events" },
]

/** Elements a hand-rolled focus trap should cycle between inside the dialog. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function CommandPalette() {
  const { navigate, runs } = useApp()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeIndex, setActiveIndex] = useState(0)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  const close = useCallback(() => {
    setOpen(false)
    setQuery("")
    setActiveIndex(0)
    setCopiedId(null)
  }, [])

  // Global shortcut, close-on-escape, and a focus trap while the dialog is open:
  // Tab/Shift+Tab cycle between the dialog's first and last focusable elements
  // instead of escaping to the page behind it.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === "Escape") close()
      if (open && e.key === "Tab") {
        const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        if (!focusable || focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [close, open])

  // Move focus into the dialog on open; restore it to whatever was focused
  // before opening (e.g. the trigger button) once it closes.
  useEffect(() => {
    if (!open) return
    previousFocusRef.current = document.activeElement as HTMLElement | null
    inputRef.current?.focus()
    return () => {
      previousFocusRef.current?.focus()
    }
  }, [open])

  const items = useMemo<PaletteItem[]>(() => {
    const navItems: PaletteItem[] = NAV_ENTRIES.map((entry) => ({
      id: `nav-${entry.label}`,
      group: "Navigate",
      label: entry.label,
      keywords: entry.keywords,
      icon: entry.icon,
      action: () => {
        navigate(entry.route)
      },
    }))

    const runItems: PaletteItem[] = runs
      .slice()
      .sort((a, b) => b.started_at.localeCompare(a.started_at))
      .slice(0, 30)
      .map((run) => ({
        id: `run-${run.run_id}`,
        group: "Runs" as const,
        label: truncateMiddle(run.run_id, 36),
        keywords: `${run.run_id} ${run.plan_id} ${run.library_id} ${run.status}`,
        icon: ListChecks,
        hint: `${run.status.replace(/_/g, " ")} · ${formatTimestamp(run.started_at)}`,
        tone: toneForStatus(run.status),
        action: () => {
          navigate({ name: "run-detail", runId: run.run_id })
        },
      }))

    const cliItems: PaletteItem[] = CLI_ENTRIES.map((entry) => ({
      id: `cli-${entry.command}`,
      group: "CLI commands",
      label: entry.command,
      keywords: `${entry.command} ${entry.description} copy cli terminal`,
      icon: SquareTerminal,
      hint: entry.description,
      action: () => {
        void navigator.clipboard.writeText(entry.command).catch(() => {})
        return "copied" as const
      },
    }))

    return [...navItems, ...runItems, ...cliItems]
  }, [navigate, runs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) {
      // Default view: nav + latest 4 runs + CLI.
      const navs = items.filter((i) => i.group === "Navigate")
      const runsShort = items.filter((i) => i.group === "Runs").slice(0, 4)
      const clis = items.filter((i) => i.group === "CLI commands")
      return [...navs, ...runsShort, ...clis]
    }
    return items.filter(
      (i) => i.label.toLowerCase().includes(q) || i.keywords.toLowerCase().includes(q),
    )
  }, [items, query])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  const runItem = useCallback(
    (item: PaletteItem) => {
      const result = item.action()
      if (result === "copied") {
        setCopiedId(item.id)
        setTimeout(() => setCopiedId(null), 1200)
      } else {
        close()
      }
    },
    [close],
  )

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      const item = filtered[activeIndex]
      if (item) runItem(item)
    }
  }

  // Keep the active option in view. CommandRow (role="option") stamps the
  // same `palette-item-<id>` id used for aria-activedescendant, so we can
  // look the active row up directly instead of a data-index attribute.
  useEffect(() => {
    const item = filtered[activeIndex]
    if (!item) return
    const el = document.getElementById(`palette-item-${item.id}`)
    el?.scrollIntoView({ block: "nearest" })
  }, [activeIndex, filtered])

  if (!open) return null

  let lastGroup: string | null = null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-[12vh]"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-xl border border-hairline bg-surface text-on-dark"
      >
        <div className="flex items-center gap-2.5 border-b border-hairline px-3.5">
          <Search className="size-4 shrink-0 text-mute" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={
              filtered[activeIndex] ? `palette-item-${filtered[activeIndex].id}` : undefined
            }
            className="h-12 w-full bg-transparent text-sm text-on-dark outline-none placeholder:text-mute"
            placeholder="Search screens, runs, CLI commands…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
          />
          <Keycap className="hidden shrink-0 sm:inline-flex">Esc</Keycap>
        </div>
        <div
          id="command-palette-list"
          ref={listRef}
          role="listbox"
          aria-label="Results"
          className="max-h-[50vh] overflow-y-auto p-1.5"
        >
          {filtered.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-mute">No results.</p>
          ) : (
            filtered.map((item, index) => {
              const showHeader = item.group !== lastGroup
              lastGroup = item.group
              const isActive = index === activeIndex
              const isCopied = copiedId === item.id
              const isRun = item.group === "Runs"
              const isCli = item.group === "CLI commands"
              return (
                <div key={item.id}>
                  {showHeader ? (
                    <p className="px-3 pb-1 pt-2.5 text-[0.625rem] font-semibold uppercase tracking-wider text-mute">
                      {item.group}
                    </p>
                  ) : null}
                  <div onMouseEnter={() => setActiveIndex(index)}>
                    <CommandRow
                      role="option"
                      id={`palette-item-${item.id}`}
                      icon={isRun ? undefined : item.icon}
                      tone={item.tone}
                      label={
                        <span
                          className={cn(item.group !== "Navigate" && "font-mono text-[0.8125rem]")}
                        >
                          {item.label}
                        </span>
                      }
                      active={isActive}
                      hint={
                        isCopied ? (
                          <span className="flex items-center gap-1 text-success">
                            <Check className="size-3.5" aria-hidden="true" /> Copied
                          </span>
                        ) : (
                          item.hint
                        )
                      }
                      keys={isCli && !isCopied ? ["Enter"] : undefined}
                      onSelect={() => runItem(item)}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>
        <div className="flex items-center gap-4 border-t border-hairline px-3.5 py-2.5 text-xs text-mute">
          <span className="flex items-center gap-1.5">
            <span className="flex items-center gap-1">
              <Keycap>↑</Keycap>
              <Keycap>↓</Keycap>
            </span>
            Navigate
          </span>
          <span className="flex items-center gap-1.5">
            <Keycap>Enter</Keycap> Select
          </span>
          <span className="flex items-center gap-1.5">
            <Keycap>Esc</Keycap> Close
          </span>
        </div>
      </div>
    </div>
  )
}

/** Header trigger for the palette (also usable on touch devices). Styled as
 * DESIGN.md's store-search-bar: surface-elevated fill, hairline border,
 * rounded-md, Ctrl K keycap hint at the trailing edge. */
export function CommandPaletteTrigger({ className }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        window.dispatchEvent(
          new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }),
        )
      }}
      aria-label="Search commands"
      className={cn(
        "inline-flex h-9 items-center gap-2.5 rounded-md border border-hairline bg-surface-elevated px-3 text-sm text-mute transition-colors hover:border-hairline-strong hover:text-on-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:h-11 sm:px-4",
        className,
      )}
    >
      <Search className="size-4 shrink-0" aria-hidden="true" />
      <span className="hidden truncate sm:inline">Search commands…</span>
      <span className="ml-auto hidden items-center gap-1 sm:flex">
        <Keycap>Ctrl</Keycap>
        <Keycap>K</Keycap>
      </span>
    </button>
  )
}
