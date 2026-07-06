"use client"

import { ArrowLeft, ClipboardList, FileDiff, Hash, ListTree } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useApp } from "../app-context"
import { formatTimestamp, truncateMiddle } from "../lib"
import type { PlanAction, PlanActionStatus } from "../types"
import { Select } from "../forms"
import {
  Button,
  CopyButton,
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  PathArrow,
  StatusBadge,
  type Column,
} from "../primitives"
import { PageHeading } from "./page-heading"

const ACTION_FILTERS: { value: PlanActionStatus | "all"; label: string }[] = [
  { value: "all", label: "All actions" },
  { value: "planned", label: "Planned" },
  { value: "blocked", label: "Blocked" },
  { value: "applied", label: "Applied" },
  { value: "failed", label: "Failed" },
]

function MetaRow({ label, value, copy }: { label: string; value: string; copy?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-0">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-center gap-1">
        <Mono className="truncate text-foreground" title={value}>
          {truncateMiddle(value, 36)}
        </Mono>
        {copy ? <CopyButton value={value} label={`Copy ${label}`} /> : null}
      </dd>
    </div>
  )
}

function hashCell(contentHash: string | null, metadataHash: string | null) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="flex items-center gap-1">
        <Hash className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
        <Mono className="truncate text-muted-foreground" title={contentHash ?? ""}>
          {contentHash ? truncateMiddle(contentHash, 18) : "—"}
        </Mono>
      </span>
      <span className="flex items-center gap-1">
        <Hash className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
        <Mono className="truncate text-muted-foreground" title={metadataHash ?? ""}>
          {metadataHash ? truncateMiddle(metadataHash, 18) : "—"}
        </Mono>
      </span>
    </div>
  )
}

export function PlanDetailScreen({ planId }: { planId: string }) {
  const { loadPlanDetail, navigate, planDetailErrors, planDetailLoading, planDetails, plans } =
    useApp()
  const [actionStatus, setActionStatus] = useState<PlanActionStatus | "all">("all")

  useEffect(() => {
    void loadPlanDetail(planId, actionStatus)
  }, [actionStatus, loadPlanDetail, planId])

  const detail = planDetails[planId]
  const errors = planDetailErrors[planId] ?? []
  const isLoaded = Object.prototype.hasOwnProperty.call(planDetails, planId) || errors.length > 0
  const isLoading = planDetailLoading[planId] ?? false
  const plan = detail?.plan ?? plans.find((candidate) => candidate.plan_id === planId) ?? null
  const actions = detail?.actions ?? []

  const counts = useMemo(() => {
    return actions.reduce(
      (acc, action) => {
        acc.total += 1
        acc[action.status] = (acc[action.status] ?? 0) + 1
        acc[action.action_type] = (acc[action.action_type] ?? 0) + 1
        return acc
      },
      { total: 0 } as Record<string, number>,
    )
  }, [actions])

  if (!plan) {
    if (!isLoaded || isLoading) {
      return (
        <>
          <PageHeading title="Plan detail" />
          <Notice tone="info" title="Loading Plan">
            Loading actions for <Mono>{planId}</Mono>.
          </Notice>
        </>
      )
    }

    return (
      <>
        <PageHeading title="Plan not found" />
        <Notice tone="danger" title="Unknown Plan">
          {errors.length > 0 ? (
            errors.join(" ")
          ) : (
            <>
              No Plan matches <Mono>{planId}</Mono>.
            </>
          )}
        </Notice>
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ name: "plans" })}>
            <ArrowLeft className="size-4" aria-hidden="true" /> Back to Plans
          </Button>
        </div>
      </>
    )
  }

  const columns: Column<PlanAction>[] = [
    {
      key: "sort_order",
      header: "#",
      cell: (action) => (
        <span className="tabular-nums text-muted-foreground">{action.sort_order}</span>
      ),
      className: "w-12",
    },
    {
      key: "status",
      header: "Status",
      cell: (action) => <StatusBadge status={action.status} iconOnly />,
      className: "w-16 text-center",
    },
    {
      key: "reason",
      header: "Reason",
      cell: (action) =>
        action.reason ? (
          <Mono className="text-warning">{action.reason}</Mono>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      className: "min-w-[10rem]",
    },
    {
      key: "action_type",
      header: "Type",
      cell: (action) => <span className="font-medium">{action.action_type}</span>,
      className: "w-36",
    },
    {
      key: "paths",
      header: "Source → Target",
      cell: (action) => (
        <PathArrow source={action.source_path ?? ""} target={action.target_path ?? ""} max={36} />
      ),
      className: "min-w-[24rem]",
    },
    {
      key: "hashes",
      header: "Hashes",
      cell: (action) => hashCell(action.content_hash_at_plan, action.metadata_hash_at_plan),
      className: "min-w-[12rem]",
    },
  ]

  return (
    <>
      <PageHeading
        title="Plan detail"
        description="Inspect recorded PlanActions and target paths before CLI apply."
        actions={
          <Button variant="outline" onClick={() => navigate({ name: "plans" })}>
            <ArrowLeft className="size-4" aria-hidden="true" /> Back
          </Button>
        }
      />

      <section
        aria-label="Plan action summary"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      >
        <MetricCard label="Shown" value={counts.total ?? 0} tone="neutral" />
        <MetricCard label="Recorded" value={detail?.total_action_count ?? 0} tone="neutral" />
        <MetricCard label="Planned" value={counts.planned ?? 0} tone="info" />
        <MetricCard label="Blocked" value={counts.blocked ?? 0} tone="danger" />
        <MetricCard label="Moves" value={counts.move ?? 0} tone="neutral" />
        <MetricCard label="Metadata" value={counts.refresh_metadata ?? 0} tone="neutral" />
      </section>

      <div className="mb-6 grid gap-6 lg:grid-cols-3">
        <Panel title="Header" icon={ClipboardList} className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <StatusBadge status={plan.status} />
            <span className="text-sm text-muted-foreground">
              {plan.plan_type} · {formatTimestamp(plan.created_at)}
            </span>
          </div>
          <dl className="grid gap-x-8 sm:grid-cols-2">
            <MetaRow label="plan_id" value={plan.plan_id} copy />
            <MetaRow label="library_id" value={plan.library_id} copy />
            {detail ? <MetaRow label="config_hash" value={detail.plan.config_hash} copy /> : null}
            {detail ? (
              <MetaRow label="library_root" value={detail.plan.library_root_at_plan} copy />
            ) : null}
          </dl>
          {errors.length > 0 ? (
            <Notice tone="warning" title="Plan detail is incomplete" className="mt-4">
              {errors.join(" ")}
            </Notice>
          ) : null}
        </Panel>

        <Panel title="Summary" icon={ListTree}>
          <dl className="rounded-md border border-border px-3">
            {Object.entries(plan.summary).map(([key, value]) => (
              <MetaRow key={key} label={key} value={value} />
            ))}
          </dl>
        </Panel>
      </div>

      <Panel
        title="Actions"
        icon={FileDiff}
        actions={
          <Select
            aria-label="Action status"
            options={ACTION_FILTERS}
            value={actionStatus}
            onChange={(event) => setActionStatus(event.target.value as PlanActionStatus | "all")}
          />
        }
      >
        <DataTable
          columns={columns}
          rows={actions}
          getRowKey={(action) => action.action_id}
          rowIsActive={(action) => action.status === "blocked" || action.status === "failed"}
          caption="Plan actions"
          empty={
            <EmptyState
              icon={FileDiff}
              title={isLoading ? "Loading actions..." : "No actions match this filter."}
            />
          }
        />
      </Panel>
    </>
  )
}
