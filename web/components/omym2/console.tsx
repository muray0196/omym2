"use client"

import { AppProvider, useApp } from "./app-context"
import { AppShell } from "./app-shell"
import { DashboardScreen } from "./screens/dashboard"
import { SettingsScreen } from "./screens/settings"
import { PathPolicyScreen } from "./screens/path-policy"
import { RunsScreen } from "./screens/runs"
import { RunDetailScreen } from "./screens/run-detail"
import { CheckScreen } from "./screens/check"
import { TracksScreen } from "./screens/tracks"

function ActiveScreen() {
  const { route } = useApp()
  switch (route.name) {
    case "dashboard":
      return <DashboardScreen />
    case "settings":
      return <SettingsScreen />
    case "path-policy":
      return <PathPolicyScreen />
    case "runs":
      return <RunsScreen />
    case "run-detail":
      return <RunDetailScreen runId={route.runId} />
    case "check":
      return <CheckScreen />
    case "tracks":
      return <TracksScreen />
    default:
      return <DashboardScreen />
  }
}

export function Console() {
  return (
    <AppProvider>
      <AppShell>
        <ActiveScreen />
      </AppShell>
    </AppProvider>
  )
}
