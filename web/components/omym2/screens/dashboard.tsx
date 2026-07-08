"use client"

import { Database, FolderTree, ListChecks, Music, ShieldCheck, Terminal } from "lucide-react"
import { useApp } from "../app-context"
import { CommandPaletteTrigger } from "../command-palette"
import { AppIconTile, CommandRow } from "../command-kit"
import { formatTimestamp, severityForIssue, truncateMiddle, validateConfig } from "../lib"
import {
  Button,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  toneForStatus,
  truncateLabel,
} from "../primitives"
import { CliCommand } from "../widgets"

export function DashboardScreen() {
  const {
    checkErrors,
    checkIssues,
    checkLoaded,
    historyErrors,
    historyLoaded,
    navigate,
    runs,
    savedConfig,
    settingsLoaded,
    settingsLoadError,
    trackErrors,
    tracks,
    tracksLoaded,
  } = useApp()
  const validation = validateConfig(savedConfig)
  // "Ready" means actually loaded from the backend. When loading finished
  // via failure, keep the placeholder values — never present the fabricated
  // default config paths as if they were the user's real settings.
  const settingsFailed = settingsLoadError !== null
  const settingsReady = settingsLoaded && !settingsFailed
  const settingsPendingHint = settingsFailed ? "Failed to load" : "Loading settings..."
  const libraryConfigured = Boolean(savedConfig.paths.library)
  const incomingConfigured = Boolean(savedConfig.paths.incoming)
  const lastRun = runs
    .filter((r) => r.status !== "running")
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
  const runningCount = runs.filter((r) => r.status === "running").length
  const issueCount = checkIssues.length
  const errorIssues = checkIssues.filter(
    (i) => (i.severity ?? severityForIssue(i.issue_type)) === "error",
  ).length
  const warningIssues = checkIssues.filter(
    (i) => (i.severity ?? severityForIssue(i.issue_type)) === "warning",
  ).length
  const knownLibraryId =
    tracks[0]?.library_id ?? runs[0]?.library_id ?? checkIssues[0]?.library_id ?? null
  const inspectionErrors = [...historyErrors, ...checkErrors, ...trackErrors]

  // Recommended next CLI command.
  const primaryCommand = !libraryConfigured
    ? { command: "omym2 settings", description: "Configure the library path before anything else." }
    : {
        command: "omym2 add",
        description: "Ready for daily import. Scans incoming files and builds a reviewable Plan.",
      }

  const recentRuns = runs
    .slice()
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 4)

  return (
    <>
      {/* Launcher header — a wordmark moment plus a prompt pointing at Ctrl K,
          echoing Raycast's root view. No hero stripe: red stays reserved
          for danger states elsewhere in the console. */}
      <div className="mb-8 flex flex-col gap-4 border-b border-hairline pb-8">
        <div className="flex items-center gap-3">
          <AppIconTile icon={Music} size={40} />
          <div>
            <h1 className="text-2xl font-medium leading-tight text-ink">OMYM2 Console</h1>
            <p className="mt-1 max-w-2xl text-pretty text-sm leading-relaxed text-mute">
              Confirm that OMYM2 is configured and consistent enough for safe CLI use. This console
              does not move files.
            </p>
          </div>
        </div>
        <CommandPaletteTrigger className="w-full max-w-md" />
      </div>

      <section
        aria-label="Readiness summary"
        className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3"
      >
        <MetricCard
          label="Settings"
          value={settingsReady ? (validation.valid ? "Valid" : "Invalid") : "—"}
          tone={settingsReady ? (validation.valid ? "success" : "danger") : "neutral"}
          hint={
            settingsReady
              ? validation.valid
                ? "All checks passed"
                : `${validation.errors.length} error(s)`
              : settingsPendingHint
          }
          icon={ShieldCheck}
        />
        <MetricCard
          label="Library"
          value={settingsReady ? (libraryConfigured ? "Configured" : "Missing") : "—"}
          tone={settingsReady ? (libraryConfigured ? "success" : "danger") : "neutral"}
          hint={
            settingsReady
              ? libraryConfigured
                ? truncateMiddle(savedConfig.paths.library!, 24)
                : "Set a path"
              : settingsPendingHint
          }
          icon={Database}
        />
        <MetricCard
          label="Incoming"
          value={settingsReady ? (incomingConfigured ? "Configured" : "Missing") : "—"}
          tone={settingsReady ? (incomingConfigured ? "success" : "warning") : "neutral"}
          hint={
            settingsReady
              ? incomingConfigured
                ? truncateMiddle(savedConfig.paths.incoming!, 24)
                : "Set a path"
              : settingsPendingHint
          }
          icon={FolderTree}
        />
        <MetricCard
          label="Last run"
          value={historyLoaded ? (lastRun ? truncateLabel(lastRun.status) : "None") : "—"}
          tone={
            !historyLoaded
              ? "neutral"
              : lastRun?.status === "succeeded"
                ? "success"
                : lastRun?.status === "failed"
                  ? "danger"
                  : lastRun?.status === "partial_failed"
                    ? "warning"
                    : "neutral"
          }
          hint={
            historyLoaded
              ? lastRun
                ? formatTimestamp(lastRun.started_at)
                : "No runs yet"
              : "Loading runs..."
          }
          icon={ListChecks}
        />
        <MetricCard
          label="Check issues"
          value={checkLoaded ? issueCount : "—"}
          tone={
            !checkLoaded
              ? "neutral"
              : errorIssues > 0
                ? "danger"
                : warningIssues > 0
                  ? "warning"
                  : "success"
          }
          hint={
            checkLoaded ? `${errorIssues} error · ${warningIssues} warning` : "Loading checks..."
          }
          icon={ShieldCheck}
        />
        <MetricCard
          label="Managed tracks"
          value={tracksLoaded ? tracks.filter((t) => t.status === "active").length : "—"}
          tone="neutral"
          hint={tracksLoaded ? `${tracks.length} total records` : "Loading tracks..."}
          icon={Music}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <Panel
            title="Recommended next CLI command"
            description="Copyable guidance only. OMYM2 performs file changes through the CLI, never from this console."
            icon={Terminal}
          >
            <div className="flex flex-col gap-3">
              {!validation.valid ? (
                <Notice tone="warning" title="Settings are invalid">
                  Resolve validation errors in Settings before running import commands.
                </Notice>
              ) : null}
              {inspectionErrors.length > 0 ? (
                <Notice tone="warning" title="Inspection data is incomplete">
                  {inspectionErrors.join(" ")}
                </Notice>
              ) : null}
              <CliCommand
                command={primaryCommand.command}
                description={primaryCommand.description}
              />
              <div className="grid gap-2 sm:grid-cols-2">
                <CliCommand command="omym2 check" description="Run consistency diagnostics." />
                <CliCommand command="omym2 history" description="Inspect past runs and events." />
              </div>
            </div>
          </Panel>

          <Panel
            title="Recent runs"
            icon={ListChecks}
            actions={
              <Button variant="outline" size="sm" onClick={() => navigate({ name: "runs" })}>
                View all
              </Button>
            }
          >
            {recentRuns.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title={historyLoaded ? "No runs recorded yet." : "Loading runs..."}
              />
            ) : (
              <div className="flex flex-col gap-1">
                {recentRuns.map((run) => (
                  <CommandRow
                    key={run.run_id}
                    tone={toneForStatus(run.status)}
                    label={
                      <Mono className="text-on-dark" title={run.run_id}>
                        {truncateMiddle(run.run_id, 32)}
                      </Mono>
                    }
                    hint={`${truncateLabel(run.status)} · ${formatTimestamp(run.started_at)}`}
                    onSelect={() => navigate({ name: "run-detail", runId: run.run_id })}
                  />
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-6">
          <Panel title="Check issue summary" icon={ShieldCheck}>
            {!checkLoaded ? (
              <Notice tone="info" title="Loading issue summary">
                Consistency diagnostics are still loading.
              </Notice>
            ) : issueCount === 0 ? (
              <Notice tone="success" title="No issues found">
                DB and filesystem state appear consistent.
              </Notice>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-md border border-hairline bg-surface-elevated p-2">
                    <p className="text-lg font-semibold tabular-nums text-danger">{errorIssues}</p>
                    <p className="text-xs text-mute">Errors</p>
                  </div>
                  <div className="rounded-md border border-hairline bg-surface-elevated p-2">
                    <p className="text-lg font-semibold tabular-nums text-warning">
                      {warningIssues}
                    </p>
                    <p className="text-xs text-mute">Warnings</p>
                  </div>
                  <div className="rounded-md border border-hairline bg-surface-elevated p-2">
                    <p className="text-lg font-semibold tabular-nums text-info">
                      {issueCount - errorIssues - warningIssues}
                    </p>
                    <p className="text-xs text-mute">Info</p>
                  </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => navigate({ name: "check" })}>
                  Open Check
                </Button>
              </div>
            )}
          </Panel>

          <Panel title="Library" icon={Database}>
            <dl className="flex flex-col gap-2.5 text-sm">
              <div className="flex items-center justify-between gap-2">
                <dt className="text-mute">Status</dt>
                <dd>
                  <StatusBadge
                    status={
                      settingsReady
                        ? libraryConfigured
                          ? "configured"
                          : "missing"
                        : settingsFailed
                          ? "unavailable"
                          : "loading"
                    }
                    label={settingsReady ? undefined : settingsFailed ? "Unavailable" : "Loading"}
                    tone={
                      settingsReady
                        ? libraryConfigured
                          ? "success"
                          : "danger"
                        : settingsFailed
                          ? "danger"
                          : "neutral"
                    }
                  />
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-mute">Library ID</dt>
                <dd>
                  {knownLibraryId ? (
                    <Mono className="text-on-dark" title={knownLibraryId}>
                      {truncateMiddle(knownLibraryId, 18)}
                    </Mono>
                  ) : (
                    <span className="text-mute">—</span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-mute">Active runs</dt>
                <dd className="font-medium tabular-nums">{historyLoaded ? runningCount : "—"}</dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  )
}
