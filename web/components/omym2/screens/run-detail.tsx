"use client"

import { ArrowLeft, FileWarning, TriangleAlert } from "lucide-react"
import { useEffect } from "react"
import { useApp } from "../app-context"
import { cn, formatDuration, formatTimestamp } from "../lib"
import type { FileEvent } from "../types"
import {
  Button,
  DataTable,
  EmptyState,
  MetaRow,
  Mono,
  Notice,
  Panel,
  PathArrow,
  StatusBadge,
  type Column,
} from "../primitives"
import { RunTimeline } from "../widgets"
import { PageHeading } from "./page-heading"

export function RunDetailScreen({ runId }: { runId: string }) {
  const { loadRunDetail, navigate, runDetailErrors, runDetailLoading, runDetails, runs } = useApp()

  useEffect(() => {
    void loadRunDetail(runId)
  }, [loadRunDetail, runId])

  const detail = runDetails[runId]
  const errors = runDetailErrors[runId] ?? []
  const isLoaded = Object.prototype.hasOwnProperty.call(runDetails, runId) || errors.length > 0
  const isLoading = runDetailLoading[runId] ?? false
  const run = detail?.run ?? runs.find((r) => r.run_id === runId)
  const events = detail?.file_events ?? []

  // "running" is the only non-terminal RunStatus. Poll this run's detail on
  // a short cadence while it's in progress, and stop once it lands on a
  // terminal status (succeeded/partial_failed/failed).
  useEffect(() => {
    if (run?.status !== "running") return
    const interval = setInterval(() => {
      void loadRunDetail(runId)
    }, 5000)
    return () => clearInterval(interval)
  }, [loadRunDetail, run?.status, runId])

  if (!run) {
    if (!isLoaded || isLoading) {
      return (
        <>
          <PageHeading title="Run detail" />
          <Notice tone="info" title="Loading run">
            Loading file events for <Mono>{runId}</Mono>.
          </Notice>
        </>
      )
    }

    return (
      <>
        <PageHeading title="Run not found" />
        <Notice tone="danger" title="Unknown run">
          {errors.length > 0 ? (
            errors.join(" ")
          ) : (
            <>
              No run matches <Mono>{runId}</Mono>.
            </>
          )}
        </Notice>
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ name: "runs" })}>
            <ArrowLeft className="size-4" aria-hidden="true" /> Back to runs
          </Button>
        </div>
      </>
    )
  }

  const failedCount = events.filter((e) => e.status === "failed").length
  const succeededCount = events.filter((e) => e.status === "succeeded").length
  // The File events table below is the single authoritative full list — this
  // digest only surfaces events that still need attention (failed/pending),
  // so it never duplicates the table's content.
  const anomalyEvents = events.filter((e) => e.status === "failed" || e.status === "pending")

  const columns: Column<FileEvent>[] = [
    {
      key: "seq",
      header: "#",
      cell: (e) => <span className="tabular-nums text-muted-foreground">{e.sequence_no}</span>,
      className: "w-10",
    },
    {
      key: "event_type",
      header: "Event",
      cell: (e) => <span>{e.event_type.replace(/_/g, " ")}</span>,
    },
    {
      key: "status",
      header: "Status",
      cell: (e) => <StatusBadge status={e.status} iconOnly />,
      className: "w-16 text-center",
    },
    {
      key: "paths",
      header: "Source → Target",
      cell: (e) => <PathArrow source={e.source_path} target={e.target_path} max={32} />,
      className: "min-w-[20rem]",
    },
    {
      key: "started",
      header: "Started",
      cell: (e) => (
        <span className="whitespace-nowrap text-muted-foreground">
          {formatTimestamp(e.started_at)}
        </span>
      ),
    },
    {
      key: "error",
      header: "Error",
      cell: (e) =>
        e.error_code ? (
          <div className="max-w-xs">
            <Mono className="text-danger">{e.error_code}</Mono>
            <p className="text-xs text-muted-foreground">{e.error_message}</p>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ]

  return (
    <>
      <PageHeading
        title="Run detail"
        description="Inspect a single apply attempt and identify which file failed and why."
        actions={
          <Button variant="outline" onClick={() => navigate({ name: "runs" })}>
            <ArrowLeft className="size-4" aria-hidden="true" /> Back
          </Button>
        }
      />

      <div className={cn("mb-6 grid gap-6", anomalyEvents.length > 0 && "lg:grid-cols-3")}>
        <Panel title="Summary" className={anomalyEvents.length > 0 ? "lg:col-span-2" : undefined}>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <StatusBadge status={run.status} />
            <span className="text-sm text-muted-foreground">
              Duration {formatDuration(run.started_at, run.completed_at)}
            </span>
          </div>
          <dl className="grid gap-x-8 sm:grid-cols-2">
            <MetaRow label="run_id" value={run.run_id} max={28} copy />
            <MetaRow label="plan_id" value={run.plan_id} max={28} copy />
            <MetaRow label="library_id" value={run.library_id} max={28} copy />
            <MetaRow label="started_at" value={formatTimestamp(run.started_at)} max={28} />
            <MetaRow label="completed_at" value={formatTimestamp(run.completed_at)} max={28} />
            <MetaRow
              label="events"
              value={`${succeededCount} ok / ${failedCount} failed`}
              max={28}
            />
          </dl>
          {run.error_summary ? (
            <Notice
              tone={run.status === "failed" ? "danger" : "warning"}
              title="Error summary"
              className="mt-4"
            >
              {run.error_summary}
            </Notice>
          ) : null}
          {errors.length > 0 ? (
            <Notice tone="warning" title="Run detail is incomplete" className="mt-4">
              {errors.join(" ")}
            </Notice>
          ) : null}
        </Panel>

        {anomalyEvents.length > 0 ? (
          <Panel
            title="Failures"
            icon={TriangleAlert}
            description="Failed and pending file events that need attention."
          >
            <RunTimeline events={anomalyEvents} />
          </Panel>
        ) : null}
      </div>

      <Panel
        title="File events"
        icon={FileWarning}
        description="Per-action filesystem events recorded during apply."
      >
        <DataTable
          columns={columns}
          rows={events}
          getRowKey={(e) => e.event_id}
          rowIsActive={(e) => e.status === "failed"}
          caption="File events"
          empty={
            <EmptyState
              icon={FileWarning}
              title="No file events were recorded."
              description="This run did not produce any filesystem events."
            />
          }
        />
      </Panel>
    </>
  )
}
