/*
Summary: Renders the OMYM2 console readiness dashboard.
Why: Summarizes settings, runs, checks, and tracks without loading full tables.
*/

"use client"

import {
  CircleAlert,
  Database,
  FolderTree,
  ListChecks,
  Music,
  Settings2,
  ShieldCheck,
  Terminal,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import {
  getCheckFacets,
  getHistoryFacets,
  getHistoryPage,
  getPlansPage,
  getTrackFacets,
  getTracksPage,
} from "../api-client"
import { useApp } from "../app-context"
import { CommandPaletteTrigger } from "../command-palette"
import { AppIconTile, CommandRow } from "../command-kit"
import { formatTimestamp, severityForIssue, truncateMiddle, validateConfig } from "../lib"
import type { CheckIssueType, PlanSummary, RunStatus, RunSummary, TrackStatus } from "../types"
import {
  Button,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  toneForStatus,
  type Tone,
  truncateLabel,
} from "../primitives"
import { CliCommand } from "../widgets"

const DASHBOARD_RUN_LIMIT = 4
const DASHBOARD_PLAN_LIMIT = 8

interface NextAction {
  icon: LucideIcon
  tone: Tone
  title: string
  description: string
  label: string
  onSelect: () => void
}

function NextActionRow({ action }: { action: NextAction }) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-hairline bg-surface-elevated p-3 sm:flex-row sm:items-center">
      <AppIconTile icon={action.icon} size={32} tone={action.tone} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{action.title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-mute">{action.description}</p>
      </div>
      <Button variant="outline" size="sm" onClick={action.onSelect}>
        {action.label}
      </Button>
    </div>
  )
}

function facetCounts<T extends string>(
  facets: Record<string, { value: string; count: number }[]>,
  field: string,
): Partial<Record<T, number>> {
  return Object.fromEntries(
    facets[field]?.map((facet) => [facet.value, facet.count]) ?? [],
  ) as Partial<Record<T, number>>
}

function sumCounts<T extends string>(counts: Partial<Record<T, number>>, values: T[]): number {
  return values.reduce((total, value) => total + (counts[value] ?? 0), 0)
}

function summaryNumber(plan: PlanSummary, key: string): number {
  const raw = plan.summary[key]
  if (!raw) return 0
  const parsed = Number.parseInt(raw, 10)
  return Number.isNaN(parsed) ? 0 : parsed
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function DashboardScreen() {
  const { navigate, savedConfig, settingsLoaded, settingsLoadError } = useApp()
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([])
  const [historyStatusCounts, setHistoryStatusCounts] = useState<
    Partial<Record<RunStatus, number>>
  >({})
  const [historyErrors, setHistoryErrors] = useState<string[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [recentPlans, setRecentPlans] = useState<PlanSummary[]>([])
  const [planErrors, setPlanErrors] = useState<string[]>([])
  const [plansLoaded, setPlansLoaded] = useState(false)
  const [checkIssueCounts, setCheckIssueCounts] = useState<Partial<Record<CheckIssueType, number>>>(
    {},
  )
  const [checkTotal, setCheckTotal] = useState<number | null>(null)
  const [checkErrors, setCheckErrors] = useState<string[]>([])
  const [checkLoaded, setCheckLoaded] = useState(false)
  const [trackStatusCounts, setTrackStatusCounts] = useState<Partial<Record<TrackStatus, number>>>(
    {},
  )
  const [trackTotal, setTrackTotal] = useState<number | null>(null)
  const [trackErrors, setTrackErrors] = useState<string[]>([])
  const [tracksLoaded, setTracksLoaded] = useState(false)
  const [trackSampleLibraryId, setTrackSampleLibraryId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadDashboardState() {
      const [
        historyPageResult,
        historyFacetsResult,
        plansPageResult,
        checkFacetsResult,
        trackFacetsResult,
        trackSampleResult,
      ] = await Promise.allSettled([
        getHistoryPage({ limit: DASHBOARD_RUN_LIMIT }),
        getHistoryFacets(),
        getPlansPage({ limit: DASHBOARD_PLAN_LIMIT }),
        getCheckFacets(),
        getTrackFacets(),
        getTracksPage({ limit: 1 }),
      ])
      if (cancelled) return

      const nextHistoryErrors: string[] = []
      if (historyPageResult.status === "fulfilled") {
        setRecentRuns(historyPageResult.value.items)
        nextHistoryErrors.push(...historyPageResult.value.errors)
      } else {
        nextHistoryErrors.push(
          errorMessage(historyPageResult.reason, "Recent run history failed to load."),
        )
      }
      if (historyFacetsResult.status === "fulfilled") {
        setHistoryStatusCounts(facetCounts<RunStatus>(historyFacetsResult.value.facets, "status"))
        nextHistoryErrors.push(...historyFacetsResult.value.errors)
      } else {
        nextHistoryErrors.push(
          errorMessage(historyFacetsResult.reason, "Run status summary failed to load."),
        )
      }
      setHistoryErrors(nextHistoryErrors)
      setHistoryLoaded(true)

      if (plansPageResult.status === "fulfilled") {
        setRecentPlans(plansPageResult.value.items)
        setPlanErrors(plansPageResult.value.errors)
      } else {
        setRecentPlans([])
        setPlanErrors([errorMessage(plansPageResult.reason, "Plan summary failed to load.")])
      }
      setPlansLoaded(true)

      if (checkFacetsResult.status === "fulfilled") {
        setCheckIssueCounts(
          facetCounts<CheckIssueType>(checkFacetsResult.value.facets, "issue_type"),
        )
        setCheckTotal(checkFacetsResult.value.total)
        setCheckErrors(checkFacetsResult.value.errors)
      } else {
        setCheckIssueCounts({})
        setCheckTotal(null)
        setCheckErrors([errorMessage(checkFacetsResult.reason, "Check summary failed to load.")])
      }
      setCheckLoaded(true)

      const nextTrackErrors: string[] = []
      if (trackFacetsResult.status === "fulfilled") {
        setTrackStatusCounts(facetCounts<TrackStatus>(trackFacetsResult.value.facets, "status"))
        setTrackTotal(trackFacetsResult.value.total)
        nextTrackErrors.push(...trackFacetsResult.value.errors)
      } else {
        setTrackStatusCounts({})
        setTrackTotal(null)
        nextTrackErrors.push(
          errorMessage(trackFacetsResult.reason, "Track summary failed to load."),
        )
      }
      if (trackSampleResult.status === "fulfilled") {
        setTrackSampleLibraryId(trackSampleResult.value.items[0]?.library_id ?? null)
        nextTrackErrors.push(...trackSampleResult.value.errors)
      } else {
        nextTrackErrors.push(errorMessage(trackSampleResult.reason, "Track sample failed to load."))
      }
      setTrackErrors(nextTrackErrors)
      setTracksLoaded(true)
    }

    void loadDashboardState()
    return () => {
      cancelled = true
    }
  }, [])

  const validation = validateConfig(savedConfig)
  // "Ready" means actually loaded from the backend. When loading finished
  // via failure, keep the placeholder values — never present the fabricated
  // default config paths as if they were the user's real settings.
  const settingsFailed = settingsLoadError !== null
  const settingsReady = settingsLoaded && !settingsFailed
  const settingsPendingHint = settingsFailed ? "Failed to load" : "Loading settings..."
  const libraryConfigured = Boolean(savedConfig.paths.library)
  const incomingConfigured = Boolean(savedConfig.paths.incoming)
  const lastRun = recentRuns
    .filter((r) => r.status !== "running")
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
  const runningCount = historyStatusCounts.running ?? 0
  const issueCount =
    checkTotal ?? Object.values(checkIssueCounts).reduce((total, count) => total + (count ?? 0), 0)
  const issueSeverityCounts = useMemo(() => {
    const counts = { error: 0, warning: 0 }
    for (const [issueType, count] of Object.entries(checkIssueCounts)) {
      const severity = severityForIssue(issueType as CheckIssueType)
      if (severity === "error" || severity === "warning") {
        counts[severity] += count ?? 0
      }
    }
    return counts
  }, [checkIssueCounts])
  const errorIssues = issueSeverityCounts.error
  const warningIssues = issueSeverityCounts.warning
  const knownLibraryId = trackSampleLibraryId ?? recentRuns[0]?.library_id ?? null
  const inspectionErrors = [...historyErrors, ...planErrors, ...checkErrors, ...trackErrors]
  const blockedPlans = recentPlans.filter((plan) => summaryNumber(plan, "blocked_actions") > 0)
  const blockedPlan = blockedPlans[0]
  const failedRun = recentRuns
    .filter((run) => run.status === "failed" || run.status === "partial_failed")
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
  const nextActions: NextAction[] = []

  if (settingsLoaded) {
    if (settingsFailed) {
      nextActions.push({
        icon: Settings2,
        tone: "danger",
        title: "Settings could not be loaded",
        description: "Open Settings to inspect the configuration before using the CLI.",
        label: "Open Settings",
        onSelect: () => navigate({ name: "settings" }),
      })
    } else if (!validation.valid || !libraryConfigured || !incomingConfigured) {
      nextActions.push({
        icon: Settings2,
        tone: "warning",
        title: "Complete settings",
        description: "Resolve the configuration gaps before creating or applying Plans.",
        label: "Open Settings",
        onSelect: () => navigate({ name: "settings" }),
      })
    }
  }

  if (checkLoaded && issueCount > 0) {
    nextActions.push({
      icon: CircleAlert,
      tone: errorIssues > 0 ? "danger" : "warning",
      title: `Review ${issueCount} check issue${issueCount === 1 ? "" : "s"}`,
      description: "Open the grouped severity view to focus on material consistency risks.",
      label: "Review issues",
      onSelect: () => navigate({ name: "check", view: "grouped", groupBy: "severity" }),
    })
  }

  if (plansLoaded && blockedPlan) {
    const blockedCount = summaryNumber(blockedPlan, "blocked_actions")
    nextActions.push({
      icon: ListChecks,
      tone: "danger",
      title: `${blockedCount} blocked Plan action${blockedCount === 1 ? "" : "s"}`,
      description: `Review the recorded blockers in this ${blockedPlan.plan_type} Plan before CLI apply.`,
      label: "Review Plan",
      onSelect: () =>
        navigate({ name: "plan-detail", planId: blockedPlan.plan_id, actionStatus: "blocked" }),
    })
  }

  if (historyLoaded && failedRun) {
    nextActions.push({
      icon: CircleAlert,
      tone: "warning",
      title: `Diagnose ${failedRun.status.replace("_", " ")} run`,
      description: "Inspect the run and its recorded file events before retrying any work.",
      label: "View run",
      onSelect: () => navigate({ name: "run-detail", runId: failedRun.run_id }),
    })
  }

  const nextActionsLoading = !settingsLoaded || !historyLoaded || !plansLoaded || !checkLoaded

  // Recommended next CLI command.
  const primaryCommand = !libraryConfigured
    ? { command: "omym2 settings", description: "Configure the library path before anything else." }
    : {
        command: "omym2 add",
        description: "Ready for daily import. Scans incoming files and builds a reviewable Plan.",
      }

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
          value={tracksLoaded ? (trackStatusCounts.active ?? 0) : "—"}
          tone="neutral"
          hint={
            tracksLoaded
              ? `${trackTotal ?? sumCounts(trackStatusCounts, ["active", "removed"])} total records`
              : "Loading tracks..."
          }
          icon={Music}
        />
      </section>

      <div className="mb-6">
        <Panel
          title="Next actions"
          description="Start with the highest-signal review path. These links open filtered or grouped views; the console never changes files."
          icon={ShieldCheck}
        >
          {nextActionsLoading ? (
            <Notice tone="info" title="Loading next actions">
              Checking settings, diagnostics, Plans, and recent runs.
            </Notice>
          ) : nextActions.length > 0 ? (
            <div className="flex flex-col gap-2">
              {nextActions.map((action) => (
                <NextActionRow key={action.title} action={action} />
              ))}
            </div>
          ) : (
            <Notice tone="success" title="No urgent review actions">
              Settings are ready and no blocked Plans or recorded check issues need attention.
            </Notice>
          )}
        </Panel>
      </div>

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
