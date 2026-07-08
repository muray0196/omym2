"use client"

import {
  Database,
  FolderTree,
  HardDrive,
  LayoutDashboard,
  ListChecks,
  Menu,
  Music,
  Plus,
  Route as RouteIcon,
  Settings,
  ShieldCheck,
  ClipboardList,
  type LucideIcon,
} from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"
import { useApp, type NavKey, type Route } from "./app-context"
import { ActionBar, AppIconTile, CommandRow, type ActionHint } from "./command-kit"
import { CommandPalette, CommandPaletteTrigger } from "./command-palette"
import { cn } from "./lib"
import { validateConfig } from "./lib"
import { Button, Mono, StatusBadge } from "./primitives"

const NAV_ITEMS: { key: NavKey; label: string; icon: LucideIcon; route: Route }[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, route: { name: "dashboard" } },
  { key: "settings", label: "Settings", icon: Settings, route: { name: "settings" } },
  { key: "path-policy", label: "Path Policy", icon: RouteIcon, route: { name: "path-policy" } },
  { key: "plans", label: "Plans", icon: ClipboardList, route: { name: "plans" } },
  { key: "runs", label: "Runs", icon: ListChecks, route: { name: "runs" } },
  { key: "check", label: "Check", icon: ShieldCheck, route: { name: "check" } },
  { key: "tracks", label: "Tracks", icon: Music, route: { name: "tracks" } },
]

// Bottom action bar — the primary-nav idiom repurposed as a footer. These are
// static affordances describing the persistent shell shortcuts (Ctrl K is
// wired up in command-palette.tsx); no new global key handlers are added here.
const GLOBAL_HINTS: ActionHint[] = [
  { keys: ["Ctrl", "K"], label: "Command palette" },
  { keys: ["Enter"], label: "Open" },
]

function activeKey(route: Route): NavKey {
  if (route.name === "run-detail") return "runs"
  if (route.name === "plan-detail") return "plans"
  return route.name
}

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { route, navigate } = useApp()
  const current = activeKey(route)
  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col overflow-y-auto border-r border-hairline bg-surface-canvas transition-[width] duration-200 lg:flex",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 border-b border-hairline py-4",
          collapsed ? "justify-center px-2" : "px-3",
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex size-8 shrink-0 items-center justify-center rounded-md text-mute transition-colors hover:bg-surface-elevated hover:text-on-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>
        {!collapsed ? (
          <>
            <AppIconTile icon={Music} size={32} />
            <div className="leading-tight">
              <p className="text-sm font-semibold text-ink">OMYM2</p>
              <p className="text-xs text-mute">Local console</p>
            </div>
          </>
        ) : null}
      </div>
      {/* Pinned command list — the seven screens rendered as command-palette
          rows with Ctrl 1…Ctrl 7 keycap hints (static affordances; Ctrl K
          remains the one wired-up global shortcut, see command-palette.tsx). */}
      <nav aria-label="Primary" className="flex flex-1 flex-col gap-0.5 p-2.5">
        {NAV_ITEMS.map((item, index) => {
          const isActive = current === item.key
          return (
            <div key={item.key} title={collapsed ? item.label : undefined}>
              <CommandRow
                icon={item.icon}
                label={collapsed ? <span className="sr-only">{item.label}</span> : item.label}
                active={isActive}
                keys={collapsed ? undefined : ["Ctrl", String(index + 1)]}
                onSelect={() => navigate(item.route)}
              />
            </div>
          )
        })}
      </nav>
      {!collapsed ? (
        <div className="border-t border-hairline p-4 text-xs text-mute">
          <p className="flex items-center gap-1.5">
            <HardDrive className="size-3.5" aria-hidden="true" />
            Execution runs through the CLI.
          </p>
        </div>
      ) : null}
    </aside>
  )
}

function MobileNav() {
  const { route, navigate } = useApp()
  const current = activeKey(route)
  return (
    <nav
      aria-label="Primary"
      className="flex gap-1 overflow-x-auto border-b border-hairline bg-surface-canvas px-2 py-2 lg:hidden"
    >
      {NAV_ITEMS.map((item) => {
        const isActive = current === item.key
        const Icon = item.icon
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => navigate(item.route)}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              isActive ? "bg-surface-active text-on-dark" : "text-mute hover:text-on-dark",
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            {item.label}
          </button>
        )
      })}
    </nav>
  )
}

function PathSummary({
  label,
  icon: Icon,
  value,
  unavailable = false,
}: {
  label: string
  icon: LucideIcon
  value: string | null
  /**
   * Settings have not resolved (still loading) or failed to load — show a
   * muted placeholder instead of "not set" or fabricated default paths.
   */
  unavailable?: boolean
}) {
  return (
    <div className="hidden items-center gap-2 rounded-md border border-hairline bg-surface-elevated px-2.5 py-1.5 xl:flex">
      <Icon className="size-4 shrink-0 text-mute" aria-hidden="true" />
      <div className="leading-tight">
        <p className="text-[0.625rem] uppercase tracking-wide text-mute">{label}</p>
        {unavailable ? (
          <span className="text-xs text-mute">—</span>
        ) : value ? (
          <Mono className="text-xs text-on-dark" title={value}>
            {value}
          </Mono>
        ) : (
          <span className="text-xs font-medium text-warning">not set</span>
        )}
      </div>
    </div>
  )
}

function Header() {
  const { route, navigate, savedConfig, settingsLoaded, settingsLoadError } = useApp()
  const validation = validateConfig(savedConfig)
  // Three settings states, not two: loading, failed ("unavailable" — never
  // show fabricated default config values as if they were real), and ready.
  const settingsFailed = settingsLoadError !== null
  const settingsReady = settingsLoaded && !settingsFailed
  const currentLabel = NAV_ITEMS.find((item) => item.key === activeKey(route))?.label ?? "Dashboard"
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-hairline bg-surface-canvas px-4 py-3 lg:px-6">
      <div className="flex items-center gap-2 lg:hidden">
        <AppIconTile icon={Music} size={28} />
        <span className="text-sm font-semibold text-ink">OMYM2</span>
      </div>
      {/* Active-screen breadcrumb. */}
      <div className="hidden items-center gap-1.5 text-sm lg:flex">
        <span className="text-mute">OMYM2</span>
        <span className="text-mute" aria-hidden="true">
          /
        </span>
        <span className="font-medium text-on-dark">{currentLabel}</span>
      </div>
      <div className="flex flex-1 flex-wrap items-center justify-end gap-2 lg:gap-3">
        <CommandPaletteTrigger />
        <Button variant="outline" size="sm" onClick={() => navigate({ name: "plans" })}>
          <Plus className="size-4" aria-hidden="true" /> New plan
        </Button>
        <PathSummary
          label="Library"
          icon={Database}
          value={savedConfig.paths.library}
          unavailable={!settingsReady}
        />
        <PathSummary
          label="Incoming"
          icon={FolderTree}
          value={savedConfig.paths.incoming}
          unavailable={!settingsReady}
        />
        <StatusBadge
          status={
            settingsReady
              ? validation.valid
                ? "valid"
                : "invalid"
              : settingsFailed
                ? "unavailable"
                : "loading"
          }
          label={
            settingsReady
              ? validation.valid
                ? "Config valid"
                : "Config invalid"
              : settingsFailed
                ? "Config unavailable"
                : "Loading"
          }
          tone={settingsReady ? undefined : settingsFailed ? "danger" : "neutral"}
        />
      </div>
    </header>
  )
}

const SIDEBAR_COLLAPSED_KEY = "omym2.sidebar-collapsed"

export function AppShell({ children }: { children: ReactNode }) {
  // Initialize to the non-collapsed default on first render (matches the
  // server-rendered markup) and apply any stored preference in a mount
  // effect, avoiding a hydration mismatch. Same pattern as the theme effect
  // in app-context.tsx.
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
      if (stored !== null) setCollapsed(stored === "true")
    } catch {
      // Ignore: localStorage can be unavailable (e.g. private browsing).
    }
  }, [])

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      } catch {
        // Ignore: localStorage can be unavailable (e.g. private browsing).
      }
      return next
    })
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface-canvas">
      <CommandPalette />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <Sidebar collapsed={collapsed} onToggle={toggleCollapsed} />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Header />
          <MobileNav />
          <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-6 lg:py-8">
            <div className="w-full">{children}</div>
          </main>
        </div>
      </div>
      <ActionBar hints={GLOBAL_HINTS} className="shrink-0" />
    </div>
  )
}
