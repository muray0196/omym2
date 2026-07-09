/*
Summary: Renders paged Run history browsing.
Why: Keeps execution history usable when stored run counts grow.
*/

"use client"

import { ChevronDown, ChevronRight, GanttChart, ListChecks, RefreshCw, Table2 } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { getHistoryFacets, getHistoryPage } from "../api-client"
import { useApp } from "../app-context"
import { cn, formatDuration, formatTimestamp, truncateMiddle } from "../lib"
import type { RunStatus, RunSummary } from "../types"
import { usePagedList } from "../use-paged-list"
import {
  Button,
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  SegmentedControl,
  StatusBadge,
  TONE_DOT_CLASSES,
  toneForStatus,
  type Column,
} from "../primitives"
import { Field, Select } from "../forms"
import { PageHeading } from "./page-heading"

const STATUS_OPTIONS: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "succeeded", label: "Succeeded" },
  { value: "running", label: "Running" },
  { value: "partial_failed", label: "Partial failed" },
  { value: "failed", label: "Failed" },
]

const RUN_PAGE_LIMIT = 50

type ViewMode = "timeline" | "table"

const VIEW_MODE_OPTIONS: { value: ViewMode; label: string; icon: typeof GanttChart }[] = [
  { value: "timeline", label: "Timeline", icon: GanttChart },
  { value: "table", label: "Table", icon: Table2 },
]

function statusFacetCounts(facets: Record<string, { value: string; count: number }[]>) {
  return Object.fromEntries(
    facets.status?.map((facet) => [facet.value, facet.count]) ?? [],
  ) as Partial<Record<RunStatus, number>>
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

/** Group runs by started date (UTC), newest first. */
function groupRunsByDay(runs: RunSummary[]): { day: string; runs: RunSummary[] }[] {
  const groups = new Map<string, RunSummary[]>()
  for (const run of runs) {
    const day = run.started_at.slice(0, 10)
    const bucket = groups.get(day)
    if (bucket) bucket.push(run)
    else groups.set(day, [run])
  }
  return Array.from(groups.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, dayRuns]) => ({ day, runs: dayRuns }))
}

function RunsTimeline({
  runs,
  onSelect,
}: {
  runs: RunSummary[]
  onSelect: (run: RunSummary) => void
}) {
  const groups = useMemo(() => groupRunsByDay(runs), [runs])
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.day} aria-label={group.day}>
          <div className="mb-2 flex items-center gap-2.5">
            <h3 className="font-mono text-xs font-semibold tabular-nums text-body">{group.day}</h3>
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
            <span className="text-xs tabular-nums text-mute">
              {group.runs.length} {group.runs.length === 1 ? "run" : "runs"}
            </span>
          </div>
          <ol className="flex flex-col">
            {group.runs.map((run, index) => {
              const isLast = index === group.runs.length - 1
              return (
                <li key={run.run_id} className="flex gap-3">
                  <div className="flex w-3.5 flex-col items-center">
                    {/* 2px tone marker — the only saturated accent on this fold. */}
                    <span
                      className={cn(
                        "mt-2 h-6 w-0.5 shrink-0 rounded-full",
                        TONE_DOT_CLASSES[toneForStatus(run.status)],
                      )}
                      aria-hidden="true"
                    />
                    {!isLast ? (
                      <span className="w-px flex-1 bg-hairline" aria-hidden="true" />
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => onSelect(run)}
                    className="group mb-2 flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-hairline bg-surface px-3 py-2 text-left transition-colors hover:bg-surface-card/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    <span className="font-mono text-xs tabular-nums text-mute">
                      {formatTimestamp(run.started_at).slice(11)}
                    </span>
                    <StatusBadge status={run.status} />
                    <Mono className="min-w-0 flex-1 truncate text-ink" title={run.run_id}>
                      {truncateMiddle(run.run_id, 28)}
                    </Mono>
                    <span className="text-xs tabular-nums text-mute">
                      {run.completed_at
                        ? formatDuration(run.started_at, run.completed_at)
                        : "running"}
                    </span>
                    {run.error_summary ? (
                      <span className="w-full truncate text-xs text-danger sm:w-auto sm:max-w-[16rem]">
                        {run.error_summary}
                      </span>
                    ) : null}
                    <ChevronRight
                      className="size-4 shrink-0 text-mute transition-transform group-hover:translate-x-0.5"
                      aria-hidden="true"
                    />
                  </button>
                </li>
              )
            })}
          </ol>
        </section>
      ))}
    </div>
  )
}

export function RunsScreen() {
  const { navigate } = useApp()
  const [status, setStatus] = useState<RunStatus | "all">("all")
  const [view, setView] = useState<ViewMode>("timeline")
  const [statusCounts, setStatusCounts] = useState<Partial<Record<RunStatus, number>>>({})
  const [facetErrors, setFacetErrors] = useState<string[]>([])

  const loadRunFacets = useCallback(async () => {
    try {
      const response = await getHistoryFacets()
      setStatusCounts(statusFacetCounts(response.facets))
      setFacetErrors(response.errors)
    } catch (error: unknown) {
      setStatusCounts({})
      setFacetErrors([errorMessage(error, "Run status summary failed to load.")])
    }
  }, [])

  useEffect(() => {
    void loadRunFacets()
  }, [loadRunFacets])

  const loadRunsPage = useCallback(
    (cursor?: string) =>
      getHistoryPage({
        cursor,
        limit: RUN_PAGE_LIMIT,
        status,
      }),
    [status],
  )
  const runsPage = usePagedList({
    errorMessage: "Run history failed to load.",
    loadPage: loadRunsPage,
  })

  const counts = useMemo(() => {
    const total = Object.values(statusCounts).reduce((sum, count) => sum + (count ?? 0), 0)
    return {
      total,
      succeeded: statusCounts.succeeded ?? 0,
      running: statusCounts.running ?? 0,
      partial_failed: statusCounts.partial_failed ?? 0,
      failed: statusCounts.failed ?? 0,
    }
  }, [statusCounts])

  const filtered = useMemo(
    () => runsPage.items.slice().sort((a, b) => b.started_at.localeCompare(a.started_at)),
    [runsPage.items],
  )

  const historyErrors = [...runsPage.errors, ...facetErrors]
  const totalRows = runsPage.page?.total ?? runsPage.items.length

  const columns: Column<RunSummary>[] = [
    {
      key: "run_id",
      header: "Run ID",
      cell: (r) => (
        <Mono className="text-ink" title={r.run_id}>
          {truncateMiddle(r.run_id, 20)}
        </Mono>
      ),
    },
    {
      key: "plan_id",
      header: "Plan ID",
      cell: (r) => (
        <Mono className="text-mute" title={r.plan_id}>
          {truncateMiddle(r.plan_id, 18)}
        </Mono>
      ),
    },
    {
      key: "library_id",
      header: "Library",
      cell: (r) => (
        <Mono className="text-mute" title={r.library_id}>
          {truncateMiddle(r.library_id, 16)}
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
      key: "started_at",
      header: "Started",
      cell: (r) => (
        <span className="whitespace-nowrap text-mute">{formatTimestamp(r.started_at)}</span>
      ),
    },
    {
      key: "completed_at",
      header: "Completed",
      cell: (r) => (
        <span className="whitespace-nowrap text-mute">
          {r.completed_at ? formatDuration(r.started_at, r.completed_at) : "—"}
        </span>
      ),
    },
    {
      key: "error_summary",
      header: "Error summary",
      cell: (r) =>
        r.error_summary ? (
          <span className="text-danger">{r.error_summary}</span>
        ) : (
          <span className="text-mute">—</span>
        ),
      className: "max-w-xs",
    },
  ]

  return (
    <>
      <PageHeading
        title="Runs"
        description="Execution history for apply attempts. Select a run to diagnose its file events."
        actions={
          <Button
            variant="outline"
            size="sm"
            aria-label="Refresh run history"
            onClick={() => {
              void runsPage.reload()
              void loadRunFacets()
            }}
          >
            <RefreshCw className="size-4" aria-hidden="true" /> Refresh
          </Button>
        }
      />

      <section
        aria-label="Run summary"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      >
        <MetricCard label="Total" value={counts.total} tone="neutral" />
        <MetricCard label="Succeeded" value={counts.succeeded} tone="success" />
        <MetricCard label="Partial failed" value={counts.partial_failed} tone="warning" />
        <MetricCard label="Failed" value={counts.failed} tone="danger" />
        <MetricCard label="Running" value={counts.running} tone="info" />
      </section>

      <Panel
        title="Run history"
        icon={ListChecks}
        className="mb-2"
        bodyClassName="flex flex-col gap-4"
        actions={
          <SegmentedControl
            ariaLabel="View mode"
            options={VIEW_MODE_OPTIONS}
            value={view}
            onChange={setView}
            size="sm"
          />
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Status">
            {(id) => (
              <Select
                id={id}
                options={STATUS_OPTIONS}
                value={status}
                onChange={(e) => setStatus(e.target.value as RunStatus | "all")}
              />
            )}
          </Field>
        </div>

        {historyErrors.length > 0 ? (
          <Notice tone="warning" title="Run history is incomplete">
            {historyErrors.join(" ")}
          </Notice>
        ) : null}

        {filtered.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title={runsPage.loaded ? "No runs match this status." : "Loading runs..."}
            description={
              runsPage.loaded
                ? "Adjust the status filter to see more results."
                : "Run history will appear here once it is loaded."
            }
          />
        ) : view === "timeline" ? (
          <RunsTimeline
            runs={filtered}
            onSelect={(r) => navigate({ name: "run-detail", runId: r.run_id })}
          />
        ) : (
          <DataTable
            columns={columns}
            rows={filtered}
            getRowKey={(r) => r.run_id}
            onRowClick={(r) => navigate({ name: "run-detail", runId: r.run_id })}
            caption="Run history"
            loadMore={{
              hasMore: runsPage.hasMore,
              loading: runsPage.loadingMore,
              onLoadMore: runsPage.loadMore,
              total: totalRows,
            }}
          />
        )}
        {view === "timeline" &&
        (filtered.length > 0 || runsPage.hasMore || runsPage.loadingMore) ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
            <span className="text-xs tabular-nums text-mute">
              {`${Math.min(runsPage.items.length, totalRows)} of ${totalRows} run${
                totalRows === 1 ? "" : "s"
              } loaded`}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!runsPage.hasMore || runsPage.loadingMore}
              onClick={runsPage.loadMore}
            >
              <ChevronDown className="size-4" aria-hidden="true" />
              {runsPage.loadingMore
                ? "Loading..."
                : runsPage.hasMore
                  ? "Load more"
                  : "All runs loaded"}
            </Button>
          </div>
        ) : null}
      </Panel>
    </>
  )
}
