/*
Summary: Renders a Run header and paged FileEvent list.
Why: Lets users diagnose apply runs without loading every event upfront.
*/

"use client"

import { ArrowLeft, ClipboardList, FileDiff, FileWarning, TriangleAlert } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { getRunEventFacets, getRunEventGroups, getRunEventsPage } from "../api-client"
import { useApp } from "../app-context"
import { cn, formatDuration, formatTimestamp } from "../lib"
import type { FileEvent, FileEventStatus, GroupCount } from "../types"
import { usePagedList } from "../use-paged-list"
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

const RUN_EVENT_PAGE_LIMIT = 100
const RUN_EVENT_GROUP_LIMIT = 5

function countFacetValues<T extends string>(
  values: { value: string; count: number }[] | undefined,
): Partial<Record<T, number>> {
  return Object.fromEntries(values?.map((facet) => [facet.value, facet.count]) ?? []) as Partial<
    Record<T, number>
  >
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function RunDetailScreen({ runId }: { runId: string }) {
  const { loadRunDetail, navigate, runDetailErrors, runDetailLoading, runDetails, runs } = useApp()
  const [eventStatusCounts, setEventStatusCounts] = useState<
    Partial<Record<FileEventStatus, number>>
  >({})
  const [eventSummaryTotal, setEventSummaryTotal] = useState<number | null>(null)
  const [eventSummaryErrors, setEventSummaryErrors] = useState<string[]>([])
  const [eventGroups, setEventGroups] = useState<GroupCount[]>([])
  const [eventGroupTotal, setEventGroupTotal] = useState<number | null>(null)
  const [eventGroupErrors, setEventGroupErrors] = useState<string[]>([])

  useEffect(() => {
    void loadRunDetail(runId)
  }, [loadRunDetail, runId])

  const detail = runDetails[runId]
  const errors = runDetailErrors[runId] ?? []
  const isLoaded = Object.prototype.hasOwnProperty.call(runDetails, runId) || errors.length > 0
  const isLoading = runDetailLoading[runId] ?? false
  const run = detail?.run ?? runs.find((r) => r.run_id === runId)
  const loadEventsPage = useCallback(
    (cursor?: string) => getRunEventsPage(runId, { cursor, limit: RUN_EVENT_PAGE_LIMIT }),
    [runId],
  )
  const eventsPage = usePagedList({
    errorMessage: "Run file events failed to load.",
    loadPage: loadEventsPage,
  })
  const events = eventsPage.items
  const loadFailedEventsPage = useCallback(
    (cursor?: string) =>
      getRunEventsPage(runId, { cursor, limit: RUN_EVENT_PAGE_LIMIT, status: "failed" }),
    [runId],
  )
  const failedEventsPage = usePagedList({
    errorMessage: "Run failed events failed to load.",
    loadPage: loadFailedEventsPage,
  })
  const loadPendingEventsPage = useCallback(
    (cursor?: string) =>
      getRunEventsPage(runId, { cursor, limit: RUN_EVENT_PAGE_LIMIT, status: "pending" }),
    [runId],
  )
  const pendingEventsPage = usePagedList({
    errorMessage: "Run pending events failed to load.",
    loadPage: loadPendingEventsPage,
  })
  const reloadEventsPage = eventsPage.reload
  const reloadFailedEventsPage = failedEventsPage.reload
  const reloadPendingEventsPage = pendingEventsPage.reload

  const refreshEventSummaries = useCallback(async () => {
    const [facetsResult, groupsResult] = await Promise.allSettled([
      getRunEventFacets(runId),
      getRunEventGroups(runId, { limit: RUN_EVENT_GROUP_LIMIT }),
    ])

    if (facetsResult.status === "fulfilled") {
      setEventStatusCounts(countFacetValues<FileEventStatus>(facetsResult.value.facets.status))
      setEventSummaryTotal(facetsResult.value.total)
      setEventSummaryErrors(facetsResult.value.errors)
    } else {
      setEventStatusCounts({})
      setEventSummaryTotal(null)
      setEventSummaryErrors([
        errorMessage(facetsResult.reason, "Run event summary failed to load."),
      ])
    }

    if (groupsResult.status === "fulfilled") {
      setEventGroups(groupsResult.value.items)
      setEventGroupTotal(groupsResult.value.page?.total ?? groupsResult.value.items.length)
      setEventGroupErrors(groupsResult.value.errors)
    } else {
      setEventGroups([])
      setEventGroupTotal(null)
      setEventGroupErrors([errorMessage(groupsResult.reason, "Run event groups failed to load.")])
    }
  }, [runId])

  useEffect(() => {
    void refreshEventSummaries()
  }, [refreshEventSummaries])

  // "running" is the only non-terminal RunStatus. Poll this run's detail on
  // a short cadence while it's in progress, including the event pages and
  // summaries because FileEvents can land while the Run header remains running.
  useEffect(() => {
    if (run?.status !== "running") return
    const interval = setInterval(() => {
      void loadRunDetail(runId)
      void reloadEventsPage()
      void reloadFailedEventsPage()
      void reloadPendingEventsPage()
      void refreshEventSummaries()
    }, 5000)
    return () => clearInterval(interval)
  }, [
    loadRunDetail,
    refreshEventSummaries,
    reloadEventsPage,
    reloadFailedEventsPage,
    reloadPendingEventsPage,
    run?.status,
    runId,
  ])

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

  const totalEventCount = eventSummaryTotal ?? eventsPage.page?.total ?? events.length
  const failedCount =
    eventStatusCounts.failed ?? failedEventsPage.page?.total ?? failedEventsPage.items.length
  const pendingCount =
    eventStatusCounts.pending ?? pendingEventsPage.page?.total ?? pendingEventsPage.items.length
  const succeededCount =
    eventStatusCounts.succeeded ?? Math.max(totalEventCount - failedCount - pendingCount, 0)
  const eventErrors = [
    ...eventsPage.errors,
    ...failedEventsPage.errors,
    ...pendingEventsPage.errors,
    ...eventSummaryErrors,
    ...eventGroupErrors,
  ]
  const anomalyEvents = [...failedEventsPage.items, ...pendingEventsPage.items].sort(
    (a, b) => a.sequence_no - b.sequence_no || a.event_id.localeCompare(b.event_id),
  )

  const columns: Column<FileEvent>[] = [
    {
      key: "seq",
      header: "#",
      cell: (e) => <span className="tabular-nums text-mute">{e.sequence_no}</span>,
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
      key: "plan_action",
      header: "Plan action",
      cell: (e) => (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() =>
            navigate({ name: "plan-detail", planId: run.plan_id, actionId: e.plan_action_id })
          }
        >
          <FileDiff className="size-3.5" aria-hidden="true" /> View action
        </Button>
      ),
      className: "min-w-[10rem]",
    },
    {
      key: "started",
      header: "Started",
      cell: (e) => (
        <span className="whitespace-nowrap text-mute">{formatTimestamp(e.started_at)}</span>
      ),
    },
    {
      key: "error",
      header: "Error",
      cell: (e) =>
        e.error_code ? (
          <div className="max-w-xs">
            <Mono className="text-danger">{e.error_code}</Mono>
            <p className="text-xs text-mute">{e.error_message}</p>
          </div>
        ) : (
          <span className="text-mute">—</span>
        ),
    },
  ]

  return (
    <>
      <PageHeading
        title="Run detail"
        description="Inspect a single apply attempt and identify which file failed and why."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => navigate({ name: "plan-detail", planId: run.plan_id })}
            >
              <ClipboardList className="size-4" aria-hidden="true" /> View Plan
            </Button>
            <Button variant="outline" onClick={() => navigate({ name: "runs" })}>
              <ArrowLeft className="size-4" aria-hidden="true" /> Back
            </Button>
          </>
        }
      />

      <div className={cn("mb-6 grid gap-6", anomalyEvents.length > 0 && "lg:grid-cols-3")}>
        <Panel title="Summary" className={anomalyEvents.length > 0 ? "lg:col-span-2" : undefined}>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <StatusBadge status={run.status} />
            <span className="text-sm text-mute">
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
              label="events_loaded"
              value={`${events.length} loaded / ${totalEventCount} recorded`}
              max={28}
            />
            <MetaRow
              label="event_status"
              value={`${succeededCount} succeeded / ${failedCount} failed / ${pendingCount} pending`}
              max={28}
            />
          </dl>
          {eventGroups.length > 0 ? (
            <div className="mt-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mute">
                Target directories
              </p>
              <div className="rounded-md border border-hairline">
                {eventGroups.map((group) => (
                  <div
                    key={group.key}
                    className="flex items-center justify-between gap-3 border-b border-hairline px-3 py-2 last:border-0"
                  >
                    <Mono className="min-w-0 truncate text-ink" title={group.label}>
                      {group.label}
                    </Mono>
                    <span className="shrink-0 tabular-nums text-mute">{group.count}</span>
                  </div>
                ))}
                {eventGroupTotal !== null && eventGroupTotal > eventGroups.length ? (
                  <div className="border-t border-hairline px-3 py-2 text-xs tabular-nums text-mute">
                    {eventGroups.length} of {eventGroupTotal} directories
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
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
          {eventErrors.length > 0 ? (
            <Notice tone="warning" title="Run file events are incomplete" className="mt-4">
              {eventErrors.join(" ")}
            </Notice>
          ) : null}
        </Panel>

        {anomalyEvents.length > 0 ? (
          <Panel
            title="Failures"
            icon={TriangleAlert}
            description="Loaded failed and pending file events that need attention."
          >
            <div className="flex flex-col gap-4">
              <RunTimeline events={anomalyEvents} />
              {failedEventsPage.hasMore || pendingEventsPage.hasMore ? (
                <div className="flex flex-wrap gap-2 border-t border-hairline pt-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!failedEventsPage.hasMore || failedEventsPage.loadingMore}
                    onClick={failedEventsPage.loadMore}
                  >
                    Load failed
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!pendingEventsPage.hasMore || pendingEventsPage.loadingMore}
                    onClick={pendingEventsPage.loadMore}
                  >
                    Load pending
                  </Button>
                </div>
              ) : null}
            </div>
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
              title={eventsPage.loaded ? "No file events were recorded." : "Loading file events..."}
              description={
                eventsPage.loaded
                  ? "This run did not produce any filesystem events."
                  : "Recorded filesystem events will appear here once they are loaded."
              }
            />
          }
          loadMore={{
            hasMore: eventsPage.hasMore,
            loading: eventsPage.loadingMore,
            onLoadMore: eventsPage.loadMore,
            total: eventsPage.page?.total ?? events.length,
          }}
        />
      </Panel>
    </>
  )
}
