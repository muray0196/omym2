"use client"

import { ArrowLeft, ClipboardList, FileDiff, Hash, ListTree } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useApp } from "../app-context"
import { describeBlockReason, formatTimestamp, truncateMiddle } from "../lib"
import type {
  PlanAction,
  PlanActionStatus,
  PlanHeader,
  PlanStatus,
  PlanSummary,
  RunSummary,
} from "../types"
import { Select } from "../forms"
import {
  Button,
  DataTable,
  EmptyState,
  MetaRow,
  MetricCard,
  Mono,
  Notice,
  Panel,
  PathArrow,
  StatusBadge,
  toneForStatus,
  type Column,
} from "../primitives"
import { CliCommand } from "../widgets"
import { PageHeading } from "./page-heading"

/** Most recent run whose plan_id matches this Plan, if any exists in context. */
function findRunForPlan(runs: RunSummary[], planId: string): RunSummary | undefined {
  return runs
    .filter((run) => run.plan_id === planId)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
}

/** Count of blocked actions from the Plan's stable summary (not the current action-status filter). */
function blockedActionCount(plan: PlanSummary): number {
  const raw = plan.summary.blocked_actions
  if (!raw) return 0
  const parsed = Number.parseInt(raw, 10)
  return Number.isNaN(parsed) ? 0 : parsed
}

/**
 * Status-driven guidance, always shown near the top of the Plan detail
 * screen. omym2's web console is a review surface, not an execution
 * screen — apply always happens via the CLI (docs/PRODUCT.md) — so this
 * panel's job is to make the next step (CLI apply, or "nothing to do
 * here") unambiguous for every terminal and non-terminal Plan status.
 */
function PlanStatusPanel({
  plan,
  onViewRun,
  runs,
}: {
  plan: PlanHeader | PlanSummary
  onViewRun: (runId: string) => void
  runs: RunSummary[]
}) {
  const status: PlanStatus = plan.status

  if (status === "ready") {
    return (
      <Notice tone="success" title="Ready to apply" className="mb-6">
        <p className="mb-2">Review the actions below, then apply from your terminal.</p>
        <CliCommand command={`omym2 apply ${plan.plan_id}`} />
      </Notice>
    )
  }

  if (status === "applying") {
    return (
      <Notice tone="info" title="Applying" className="mb-6">
        This Plan is currently being applied. Refresh Runs shortly to see the result.
      </Notice>
    )
  }

  if (status === "applied" || status === "partial_failed" || status === "failed") {
    const matchingRun = findRunForPlan(runs, plan.plan_id)
    const title =
      status === "applied"
        ? "Applied"
        : status === "partial_failed"
          ? "Partially applied"
          : "Apply failed"
    const body =
      status === "applied"
        ? "All actions in this Plan were applied."
        : "Some actions in this Plan did not apply successfully. Check the run's file events to diagnose what went wrong."
    return (
      <Notice tone={toneForStatus(status)} title={title} className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>{body}</span>
          {matchingRun ? (
            <Button variant="outline" size="sm" onClick={() => onViewRun(matchingRun.run_id)}>
              View run
            </Button>
          ) : null}
        </div>
      </Notice>
    )
  }

  // cancelled / expired
  return (
    <Notice tone="neutral" title="No longer actionable" className="mb-6">
      This Plan is a single-use snapshot and cannot be applied again.
    </Notice>
  )
}

const ACTION_FILTERS: { value: PlanActionStatus | "all"; label: string }[] = [
  { value: "all", label: "All actions" },
  { value: "planned", label: "Planned" },
  { value: "blocked", label: "Blocked" },
  { value: "applied", label: "Applied" },
  { value: "failed", label: "Failed" },
]

function hashCell(contentHash: string | null, metadataHash: string | null) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="flex items-center gap-1">
        <Hash className="size-3 shrink-0 text-mute" aria-hidden="true" />
        <Mono className="truncate text-mute" title={contentHash ?? ""}>
          {contentHash ? truncateMiddle(contentHash, 18) : "—"}
        </Mono>
      </span>
      <span className="flex items-center gap-1">
        <Hash className="size-3 shrink-0 text-mute" aria-hidden="true" />
        <Mono className="truncate text-mute" title={metadataHash ?? ""}>
          {metadataHash ? truncateMiddle(metadataHash, 18) : "—"}
        </Mono>
      </span>
    </div>
  )
}

export function PlanDetailScreen({ planId }: { planId: string }) {
  const {
    loadPlanDetail,
    navigate,
    planDetailErrors,
    planDetailLoading,
    planDetails,
    plans,
    runs,
  } = useApp()
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

  const blockedCount = blockedActionCount(plan)

  const columns: Column<PlanAction>[] = [
    {
      key: "sort_order",
      header: "#",
      cell: (action) => <span className="tabular-nums text-mute">{action.sort_order}</span>,
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
      cell: (action) => {
        if (!action.reason) return <span className="text-mute">—</span>
        const described = describeBlockReason(action.reason)
        // Unknown reasons fall back to the raw snake_case string — keep the
        // Mono treatment for those; humanized text reads as a sentence.
        return described === action.reason ? (
          <Mono className="text-warning" title={action.reason}>
            {action.reason}
          </Mono>
        ) : (
          <span className="text-warning" title={action.reason}>
            {described}
          </span>
        )
      },
      className: "min-w-[14rem]",
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

      <PlanStatusPanel
        plan={plan}
        runs={runs}
        onViewRun={(runId) => navigate({ name: "run-detail", runId })}
      />

      {blockedCount > 0 ? (
        <Notice
          tone="danger"
          title={`${blockedCount} blocked action${blockedCount === 1 ? "" : "s"}`}
          className="mb-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>These actions cannot be applied until the underlying issue is resolved.</span>
            <Button variant="outline" size="sm" onClick={() => setActionStatus("blocked")}>
              View blocked actions
            </Button>
          </div>
        </Notice>
      ) : null}

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
            <span className="text-sm text-mute">
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
          <dl className="rounded-md border border-hairline px-3">
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
