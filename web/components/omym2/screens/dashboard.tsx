"use client"

import { Database, FolderTree, ListChecks, Music, ShieldCheck, Terminal } from "lucide-react"
import { useApp } from "../app-context"
import { formatTimestamp, severityForIssue, truncateMiddle, validateConfig } from "../lib"
import {
  Button,
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  truncateLabel,
  type Column,
} from "../primitives"
import { CliCommand } from "../widgets"
import { PageHeading } from "./page-heading"
import type { RunSummary } from "../types"

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

  const runColumns: Column<RunSummary>[] = [
    {
      key: "run_id",
      header: "Run",
      cell: (r) => (
        <Mono className="text-foreground" title={r.run_id}>
          {truncateMiddle(r.run_id, 22)}
        </Mono>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => <StatusBadge status={r.status} iconOnly />,
      className: "w-16 text-center",
    },
    {
      key: "started",
      header: "Started",
      cell: (r) => <span className="text-muted-foreground">{formatTimestamp(r.started_at)}</span>,
      className: "whitespace-nowrap",
    },
  ]

  return (
    <>
      <PageHeading
        title="Dashboard"
        description="Confirm that OMYM2 is configured and consistent enough for safe CLI use. This console does not move files."
      />

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
            <DataTable
              columns={runColumns}
              rows={recentRuns}
              getRowKey={(r) => r.run_id}
              onRowClick={(r) => navigate({ name: "run-detail", runId: r.run_id })}
              caption="Most recent runs"
              empty={
                <EmptyState
                  icon={ListChecks}
                  title={historyLoaded ? "No runs recorded yet." : "Loading runs..."}
                />
              }
            />
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
                  <div className="rounded-md border border-border p-2">
                    <p className="text-lg font-semibold tabular-nums text-danger">{errorIssues}</p>
                    <p className="text-xs text-muted-foreground">Errors</p>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <p className="text-lg font-semibold tabular-nums text-warning">
                      {warningIssues}
                    </p>
                    <p className="text-xs text-muted-foreground">Warnings</p>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <p className="text-lg font-semibold tabular-nums text-info">
                      {issueCount - errorIssues - warningIssues}
                    </p>
                    <p className="text-xs text-muted-foreground">Info</p>
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
                <dt className="text-muted-foreground">Status</dt>
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
                <dt className="text-muted-foreground">Library ID</dt>
                <dd>
                  {knownLibraryId ? (
                    <Mono className="text-foreground" title={knownLibraryId}>
                      {truncateMiddle(knownLibraryId, 18)}
                    </Mono>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-muted-foreground">Active runs</dt>
                <dd className="font-medium tabular-nums">{historyLoaded ? runningCount : "—"}</dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  )
}
