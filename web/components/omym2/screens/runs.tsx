"use client"

import { ListChecks, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { formatDuration, formatTimestamp, truncateMiddle } from "../lib"
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

export function RunsScreen() {
  const { historyErrors, historyLoaded, navigate, runs } = useApp()
  const [status, setStatus] = useState("all")
  const [query, setQuery] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")

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
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
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

        <DataTable
          columns={columns}
          rows={filtered}
          getRowKey={(r) => r.run_id}
          onRowClick={(r) => navigate({ name: "run-detail", runId: r.run_id })}
          caption="Run history"
          empty={
            <EmptyState
              icon={ListChecks}
              title={historyLoaded ? "No runs match your filters." : "Loading runs..."}
              description={
                historyLoaded
                  ? "Adjust the status, date range, or search query to see more results."
                  : "Run history will appear here once it is loaded."
              }
            />
          }
        />
      </Panel>
    </>
  )
}
