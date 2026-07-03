"use client"

import {
  Database,
  FolderTree,
  HardDrive,
  LayoutDashboard,
  ListChecks,
  Menu,
  Music,
  Route as RouteIcon,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react"
import { type ReactNode, useState } from "react"
import { useApp, type NavKey, type Route } from "./app-context"
import { CommandPalette, CommandPaletteTrigger } from "./command-palette"
import { cn } from "./lib"
import { validateConfig } from "./lib"
import { Mono, StatusBadge } from "./primitives"

const NAV_ITEMS: { key: NavKey; label: string; icon: LucideIcon; route: Route }[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, route: { name: "dashboard" } },
  { key: "settings", label: "Settings", icon: Settings, route: { name: "settings" } },
  { key: "path-policy", label: "Path Policy", icon: RouteIcon, route: { name: "path-policy" } },
  { key: "runs", label: "Runs", icon: ListChecks, route: { name: "runs" } },
  { key: "check", label: "Check", icon: ShieldCheck, route: { name: "check" } },
  { key: "tracks", label: "Tracks", icon: Music, route: { name: "tracks" } },
]

function activeKey(route: Route): NavKey {
  if (route.name === "run-detail") return "runs"
  return route.name
}

function Sidebar({ collapsed }: { collapsed: boolean }) {
  const { route, navigate } = useApp()
  const current = activeKey(route)
  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col overflow-y-auto border-r border-sidebar-border bg-sidebar transition-[width] duration-200 lg:flex",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2.5 border-b border-sidebar-border py-4",
          collapsed ? "justify-center px-2" : "px-5",
        )}
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Music className="size-4" aria-hidden="true" />
        </div>
        {!collapsed ? (
          <div className="leading-tight">
            <p className="text-sm font-semibold text-sidebar-foreground">OMYM2</p>
            <p className="text-xs text-muted-foreground">Local console</p>
          </div>
        ) : null}
      </div>
      <nav aria-label="Primary" className="flex flex-1 flex-col gap-0.5 p-3">
        {NAV_ITEMS.map((item) => {
          const isActive = current === item.key
          const Icon = item.icon
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => navigate(item.route)}
              aria-current={isActive ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sidebar-ring",
                collapsed ? "justify-center px-0" : "px-3",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden="true" />
              {collapsed ? <span className="sr-only">{item.label}</span> : item.label}
            </button>
          )
        })}
      </nav>
      {!collapsed ? (
        <div className="border-t border-sidebar-border p-4 text-xs text-muted-foreground">
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
      className="flex gap-1 overflow-x-auto border-b border-border bg-card px-2 py-2 lg:hidden"
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
              isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground",
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
}: {
  label: string
  icon: LucideIcon
  value: string | null
}) {
  return (
    <div className="hidden items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 xl:flex">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="leading-tight">
        <p className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">{label}</p>
        {value ? (
          <Mono className="text-xs text-foreground" title={value}>
            {value}
          </Mono>
        ) : (
          <span className="text-xs font-medium text-warning">not set</span>
        )}
      </div>
    </div>
  )
}

function Header({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { savedConfig } = useApp()
  const validation = validateConfig(savedConfig)
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-background/80 px-4 py-3 backdrop-blur lg:px-6">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          className="hidden items-center justify-center rounded-md border border-border bg-card p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring lg:inline-flex"
        >
          <Menu className="size-4" aria-hidden="true" />
        </button>
        <div className="flex items-center gap-2 lg:hidden">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Music className="size-4" aria-hidden="true" />
          </div>
          <span className="text-sm font-semibold">OMYM2</span>
        </div>
      </div>
      <div className="flex flex-1 flex-wrap items-center justify-end gap-2 lg:gap-3">
        <CommandPaletteTrigger />
        <PathSummary label="Library" icon={Database} value={savedConfig.paths.library} />
        <PathSummary label="Incoming" icon={FolderTree} value={savedConfig.paths.incoming} />
        <StatusBadge
          status={validation.valid ? "valid" : "invalid"}
          label={validation.valid ? "Config valid" : "Config invalid"}
        />
      </div>
    </header>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <CommandPalette />
      <Sidebar collapsed={collapsed} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header onToggleSidebar={() => setCollapsed((v) => !v)} />
        <MobileNav />
        <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-6 lg:py-8">
          <div className="w-full">{children}</div>
        </main>
      </div>
    </div>
  )
}
