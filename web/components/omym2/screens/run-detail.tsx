"use client"

import { ArrowLeft, Clock, FileWarning } from "lucide-react"
import { useEffect } from "react"
import { useApp } from "../app-context"
import { formatDuration, formatTimestamp, truncateMiddle } from "../lib"
import type { FileEvent } from "../types"
import {
  Button,
  CopyButton,
  DataTable,
  EmptyState,
  Mono,
  Notice,
  Panel,
  PathArrow,
  StatusBadge,
  type Column,
} from "../primitives"
import { RunTimeline } from "../widgets"
import { PageHeading } from "./page-heading"

function MetaRow({ label, value, copy }: { label: string; value: string; copy?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-0">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-center gap-1">
        <Mono className="truncate text-foreground" title={value}>
          {truncateMiddle(value, 28)}
        </Mono>
        {copy ? <CopyButton value={value} label={`Copy ${label}`} /> : null}
      </dd>
    </div>
  )
}

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
    { key: "status", header: "Status", cell: (e) => <StatusBadge status={e.status} /> },
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

      <div className="mb-6 grid gap-6 lg:grid-cols-3">
        <Panel title="Summary" className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <StatusBadge status={run.status} />
            <span className="text-sm text-muted-foreground">
              Duration {formatDuration(run.started_at, run.completed_at)}
            </span>
          </div>
          <dl className="grid gap-x-8 sm:grid-cols-2">
            <MetaRow label="run_id" value={run.run_id} copy />
            <MetaRow label="plan_id" value={run.plan_id} copy />
            <MetaRow label="library_id" value={run.library_id} copy />
            <MetaRow label="started_at" value={formatTimestamp(run.started_at)} />
            <MetaRow label="completed_at" value={formatTimestamp(run.completed_at)} />
            <MetaRow label="events" value={`${succeededCount} ok / ${failedCount} failed`} />
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

        <Panel title="Execution timeline" icon={Clock}>
          <RunTimeline events={events} />
        </Panel>
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
