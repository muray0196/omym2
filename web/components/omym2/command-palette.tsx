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

const TONE_DOT: Record<Tone, string> = {
  success: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-muted-foreground",
}

export function CommandPalette() {
  const { navigate, runs } = useApp()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeIndex, setActiveIndex] = useState(0)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const close = useCallback(() => {
    setOpen(false)
    setQuery("")
    setActiveIndex(0)
    setCopiedId(null)
  }, [])

  // Global shortcut.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === "Escape") close()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [close])

  useEffect(() => {
    if (open) inputRef.current?.focus()
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

  // Keep the active option in view.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
    el?.scrollIntoView({ block: "nearest" })
  }, [activeIndex])

  if (!open) return null

  let lastGroup: string | null = null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/30 px-4 pt-[12vh] backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-2xl"
      >
        <div className="flex items-center gap-2.5 border-b border-border px-3.5">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={
              filtered[activeIndex] ? `palette-item-${filtered[activeIndex].id}` : undefined
            }
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            placeholder="Search screens, runs, CLI commands…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
          />
          <kbd className="hidden shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.625rem] text-muted-foreground sm:block">
            esc
          </kbd>
        </div>
        <div
          id="command-palette-list"
          ref={listRef}
          role="listbox"
          aria-label="Results"
          className="max-h-[50vh] overflow-y-auto p-1.5"
        >
          {filtered.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">No results.</p>
          ) : (
            filtered.map((item, index) => {
              const showHeader = item.group !== lastGroup
              lastGroup = item.group
              const Icon = item.icon
              const isActive = index === activeIndex
              const isCopied = copiedId === item.id
              return (
                <div key={item.id}>
                  {showHeader ? (
                    <p className="px-3 pb-1 pt-2.5 text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground">
                      {item.group}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    id={`palette-item-${item.id}`}
                    role="option"
                    aria-selected={isActive}
                    data-index={index}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => runItem(item)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors",
                      isActive ? "bg-accent text-accent-foreground" : "text-foreground",
                    )}
                  >
                    <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate",
                        item.group !== "Navigate" && "font-mono text-[0.8125rem]",
                      )}
                    >
                      {item.label}
                    </span>
                    {item.tone ? (
                      <span
                        className={cn("size-2 shrink-0 rounded-full", TONE_DOT[item.tone])}
                        aria-hidden="true"
                      />
                    ) : null}
                    {isCopied ? (
                      <span className="flex shrink-0 items-center gap-1 text-xs text-success">
                        <Check className="size-3.5" aria-hidden="true" /> Copied
                      </span>
                    ) : item.hint ? (
                      <span className="shrink-0 text-xs text-muted-foreground">{item.hint}</span>
                    ) : null}
                  </button>
                </div>
              )
            })
          )}
        </div>
        <div className="flex items-center gap-3 border-t border-border px-3.5 py-2 text-[0.6875rem] text-muted-foreground">
          <span>
            <kbd className="rounded border border-border bg-muted px-1 font-mono">↑↓</kbd> navigate
          </span>
          <span>
            <kbd className="rounded border border-border bg-muted px-1 font-mono">↵</kbd> select /
            copy
          </span>
        </div>
      </div>
    </div>
  )
}

/** Header trigger for the palette (also usable on touch devices). */
export function CommandPaletteTrigger({ className }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        window.dispatchEvent(
          new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }),
        )
      }}
      className={cn(
        "inline-flex h-8 items-center gap-2 rounded-md border border-border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
    >
      <Search className="size-3.5" aria-hidden="true" />
      <span className="hidden sm:inline">Search</span>
      <kbd className="rounded border border-border bg-muted px-1 font-mono text-[0.625rem]">⌘K</kbd>
    </button>
  )
}
