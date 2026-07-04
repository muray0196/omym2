"use client"

import { ChevronRight, GanttChart, ListChecks, Search, Table2 } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { cn, formatDuration, formatTimestamp, truncateMiddle } from "../lib"
import type { RunStatus, RunSummary } from "../types"
import {
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  type Column,
} from "../primitives"
import { Field, Select, TextInput } from "../forms"
import { PageHeading } from "./page-heading"

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "succeeded", label: "Succeeded" },
  { value: "running", label: "Running" },
  { value: "partial_failed", label: "Partial failed" },
  { value: "failed", label: "Failed" },
]

const STATUS_MARKER: Record<RunStatus, string> = {
  succeeded: "border-success bg-success",
  running: "border-info bg-info",
  partial_failed: "border-warning bg-warning",
  failed: "border-danger bg-danger",
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
            <h3 className="font-mono text-xs font-semibold tabular-nums text-foreground">
              {group.day}
            </h3>
            <span className="h-px flex-1 bg-border" aria-hidden="true" />
            <span className="text-xs tabular-nums text-muted-foreground">
              {group.runs.length} {group.runs.length === 1 ? "run" : "runs"}
            </span>
          </div>
          <ol className="flex flex-col">
            {group.runs.map((run, index) => {
              const isLast = index === group.runs.length - 1
              return (
                <li key={run.run_id} className="flex gap-3">
                  <div className="flex w-3.5 flex-col items-center">
                    <span
                      className={cn(
                        "mt-2.5 size-3 shrink-0 rounded-full border-2",
                        STATUS_MARKER[run.status],
                      )}
                      aria-hidden="true"
                    />
                    {!isLast ? <span className="w-px flex-1 bg-border" aria-hidden="true" /> : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => onSelect(run)}
                    className="group mb-2 flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-card px-3 py-2 text-left transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    <span className="font-mono text-xs tabular-nums text-muted-foreground">
                      {formatTimestamp(run.started_at).slice(11)}
                    </span>
                    <StatusBadge status={run.status} />
                    <Mono className="min-w-0 flex-1 truncate text-foreground" title={run.run_id}>
                      {truncateMiddle(run.run_id, 28)}
                    </Mono>
                    <span className="text-xs tabular-nums text-muted-foreground">
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
                      className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
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
  const { historyErrors, historyLoaded, navigate, runs } = useApp()
  const [status, setStatus] = useState("all")
  const [query, setQuery] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [view, setView] = useState<"timeline" | "table">("timeline")

  const counts = useMemo(() => {
    const base: Record<RunStatus | "total", number> = {
      total: runs.length,
      succeeded: 0,
      running: 0,
      partial_failed: 0,
      failed: 0,
    }
    for (const r of runs) base[r.status]++
    return base
  }, [runs])

  const filtered = useMemo(() => {
    return runs
      .filter((r) => (status === "all" ? true : r.status === status))
      .filter((r) => {
        if (!query.trim()) return true
        const q = query.toLowerCase()
        return (
          r.run_id.toLowerCase().includes(q) ||
          r.plan_id.toLowerCase().includes(q) ||
          r.library_id.toLowerCase().includes(q)
        )
      })
      .filter((r) => {
        if (from && r.started_at.slice(0, 10) < from) return false
        if (to && r.started_at.slice(0, 10) > to) return false
        return true
      })
      .sort((a, b) => b.started_at.localeCompare(a.started_at))
  }, [from, query, runs, status, to])

  const columns: Column<RunSummary>[] = [
    {
      key: "run_id",
      header: "Run ID",
      cell: (r) => (
        <Mono className="text-foreground" title={r.run_id}>
          {truncateMiddle(r.run_id, 20)}
        </Mono>
      ),
    },
    {
      key: "plan_id",
      header: "Plan ID",
      cell: (r) => (
        <Mono className="text-muted-foreground" title={r.plan_id}>
          {truncateMiddle(r.plan_id, 18)}
        </Mono>
      ),
    },
    {
      key: "library_id",
      header: "Library",
      cell: (r) => (
        <Mono className="text-muted-foreground" title={r.library_id}>
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
        <span className="whitespace-nowrap text-muted-foreground">
          {formatTimestamp(r.started_at)}
        </span>
      ),
    },
    {
      key: "completed_at",
      header: "Completed",
      cell: (r) => (
        <span className="whitespace-nowrap text-muted-foreground">
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
          <span className="text-muted-foreground">—</span>
        ),
      className: "max-w-xs",
    },
  ]

  return (
    <>
      <PageHeading
        title="Runs"
        description="Execution history for apply attempts. Select a run to diagnose its file events."
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
          <div
            role="group"
            aria-label="View mode"
            className="flex rounded-md border border-border bg-muted p-0.5"
          >
            <button
              type="button"
              onClick={() => setView("timeline")}
              aria-pressed={view === "timeline"}
              className={cn(
                "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                view === "timeline"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <GanttChart className="size-3.5" aria-hidden="true" />
              Timeline
            </button>
            <button
              type="button"
              onClick={() => setView("table")}
              aria-pressed={view === "table"}
              className={cn(
                "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                view === "table"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Table2 className="size-3.5" aria-hidden="true" />
              Table
            </button>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Search" help="Match run_id, plan_id, or library_id.">
            {(id) => (
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <TextInput
                  id={id}
                  className="pl-8"
                  placeholder="run_… / plan_… / lib_…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            )}
          </Field>
          <Field label="Status">
            {(id) => (
              <Select
                id={id}
                options={STATUS_OPTIONS}
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              />
            )}
          </Field>
          <Field label="From date">
            {(id) => (
              <TextInput
                id={id}
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            )}
          </Field>
          <Field label="To date">
            {(id) => (
              <TextInput id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />
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
            title={historyLoaded ? "No runs match your filters." : "Loading runs..."}
            description={
              historyLoaded
                ? "Adjust the status, date range, or search query to see more results."
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
          />
        )}
      </Panel>
    </>
  )
}
