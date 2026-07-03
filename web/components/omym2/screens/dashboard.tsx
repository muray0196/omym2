"use client"

import { Database, FolderTree, ListChecks, Music, ShieldCheck, Terminal } from "lucide-react"
import { useApp } from "../app-context"
import { formatTimestamp, severityForIssue, truncateMiddle, validateConfig } from "../lib"
import {
  Button,
  DataTable,
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
    historyErrors,
    navigate,
    runs,
    savedConfig,
    trackErrors,
    tracks,
  } = useApp()
  const validation = validateConfig(savedConfig)
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
          value={validation.valid ? "Valid" : "Invalid"}
          tone={validation.valid ? "success" : "danger"}
          hint={validation.valid ? "All checks passed" : `${validation.errors.length} error(s)`}
          icon={ShieldCheck}
        />
        <MetricCard
          label="Library"
          value={libraryConfigured ? "Configured" : "Missing"}
          tone={libraryConfigured ? "success" : "danger"}
          hint={libraryConfigured ? truncateMiddle(savedConfig.paths.library!, 24) : "Set a path"}
          icon={Database}
        />
        <MetricCard
          label="Incoming"
          value={incomingConfigured ? "Configured" : "Missing"}
          tone={incomingConfigured ? "success" : "warning"}
          hint={incomingConfigured ? truncateMiddle(savedConfig.paths.incoming!, 24) : "Set a path"}
          icon={FolderTree}
        />
        <MetricCard
          label="Last run"
          value={lastRun ? truncateLabel(lastRun.status) : "None"}
          tone={
            lastRun?.status === "succeeded"
              ? "success"
              : lastRun?.status === "failed"
                ? "danger"
                : lastRun?.status === "partial_failed"
                  ? "warning"
                  : "neutral"
          }
          hint={lastRun ? formatTimestamp(lastRun.started_at) : "No runs yet"}
          icon={ListChecks}
        />
        <MetricCard
          label="Check issues"
          value={issueCount}
          tone={errorIssues > 0 ? "danger" : warningIssues > 0 ? "warning" : "success"}
          hint={`${errorIssues} error · ${warningIssues} warning`}
          icon={ShieldCheck}
        />
        <MetricCard
          label="Managed tracks"
          value={tracks.filter((t) => t.status === "active").length}
          tone="neutral"
          hint={`${tracks.length} total records`}
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
            />
          </Panel>
        </div>

        <div className="flex flex-col gap-6">
          <Panel title="Check issue summary" icon={ShieldCheck}>
            {issueCount === 0 ? (
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
                  <StatusBadge status={libraryConfigured ? "configured" : "missing"} />
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
                <dd className="font-medium tabular-nums">{runningCount}</dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  )
}
