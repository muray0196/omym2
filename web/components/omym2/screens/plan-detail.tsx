/*
Summary: Renders a Plan header, risk summary, and grouped/table/diff action review.
Why: Lets a Plan with thousands of actions read as library operations before CLI apply.
*/

"use client"

import { ArrowLeft, ClipboardList, ListTree } from "lucide-react"
import { useEffect, useState } from "react"
import { getHistoryPage, getPlanFacets } from "../api-client"
import { useApp } from "../app-context"
import { formatTimestamp } from "../lib"
import type { PlanActionStatus, PlanHeader, PlanStatus, PlanSummary, RunSummary } from "../types"
import {
  Button,
  MetaRow,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  toneForStatus,
} from "../primitives"
import { CliCommand } from "../widgets"
import { PageHeading } from "./page-heading"
import { PlanActionsPanel, type PlanViewMode } from "./plan-detail-actions"

/** Most recent run whose plan_id matches this Plan, if any exists in context. */
function findRunForPlan(runs: RunSummary[], planId: string): RunSummary | undefined {
  return runs
    .filter((run) => run.plan_id === planId)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
}

function summaryNumber(plan: PlanHeader | PlanSummary, key: string): number {
  const raw = plan.summary[key]
  if (!raw) return 0
  const parsed = Number.parseInt(raw, 10)
  return Number.isNaN(parsed) ? 0 : parsed
}

/** Count of blocked actions from the Plan's stable summary (not the current action-status filter). */
function blockedActionCount(plan: PlanSummary): number {
  return summaryNumber(plan, "blocked_actions")
}

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
  const [viewMode, setViewMode] = useState<PlanViewMode>("grouped")
  const [actionStatus, setActionStatus] = useState<PlanActionStatus | "all">("all")
  const [actionStatusCounts, setActionStatusCounts] = useState<
    Partial<Record<PlanActionStatus, number>>
  >({})
  const [actionReasonCounts, setActionReasonCounts] = useState<Partial<Record<string, number>>>({})
  const [targetCollisions, setTargetCollisions] = useState<number | null>(null)
  const [actionFacetTotal, setActionFacetTotal] = useState<number | null>(null)
  const [actionFacetErrors, setActionFacetErrors] = useState<string[]>([])
  const [matchingRun, setMatchingRun] = useState<RunSummary | null>(null)
  const [matchingRunErrors, setMatchingRunErrors] = useState<string[]>([])

  useEffect(() => {
    void loadPlanDetail(planId)
  }, [loadPlanDetail, planId])

  useEffect(() => {
    let cancelled = false
    setActionFacetErrors([])
    getPlanFacets(planId)
      .then((response) => {
        if (cancelled) return
        setActionStatusCounts(countFacetValues<PlanActionStatus>(response.facets.status))
        setActionReasonCounts(countFacetValues(response.facets.reason))
        setTargetCollisions(response.target_collisions)
        setActionFacetTotal(response.total)
        setActionFacetErrors(response.errors)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setActionStatusCounts({})
        setActionReasonCounts({})
        setTargetCollisions(null)
        setActionFacetTotal(null)
        setActionFacetErrors([errorMessage(error, "Plan action summary failed to load.")])
      })
    return () => {
      cancelled = true
    }
  }, [planId])

  const detail = planDetails[planId]
  const errors = planDetailErrors[planId] ?? []
  const isLoaded = Object.prototype.hasOwnProperty.call(planDetails, planId) || errors.length > 0
  const isLoading = planDetailLoading[planId] ?? false
  const plan = detail?.plan ?? plans.find((candidate) => candidate.plan_id === planId) ?? null
  const runCandidates = matchingRun
    ? [matchingRun, ...runs.filter((candidate) => candidate.run_id !== matchingRun.run_id)]
    : runs

  useEffect(() => {
    if (!plan || !["applied", "partial_failed", "failed"].includes(plan.status)) {
      setMatchingRun(null)
      setMatchingRunErrors([])
      return
    }

    let cancelled = false
    setMatchingRunErrors([])
    getHistoryPage({ planId, limit: 1 })
      .then((response) => {
        if (cancelled) return
        setMatchingRun(response.items[0] ?? null)
        setMatchingRunErrors(response.errors)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setMatchingRun(null)
        setMatchingRunErrors([errorMessage(error, "Matching run failed to load.")])
      })

    return () => {
      cancelled = true
    }
  }, [plan, planId])

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
  const recordedActionCount = actionFacetTotal ?? summaryNumber(plan, "action_count")
  // Risk metrics prefer live facet data; blocked falls back to the Plan's
  // stable summary so the strip stays meaningful while facets load.
  const riskBlockedCount = actionStatusCounts.blocked ?? blockedCount
  const unknownMetadataCount = actionReasonCounts["missing_required_metadata"] ?? 0
  const collisionCount = targetCollisions ?? 0

  return (
    <>
      <PageHeading
        title="Plan detail"
        description="Review recorded PlanActions as grouped library operations before CLI apply."
        actions={
          <Button variant="outline" onClick={() => navigate({ name: "plans" })}>
            <ArrowLeft className="size-4" aria-hidden="true" /> Back
          </Button>
        }
      />

      <PlanStatusPanel
        plan={plan}
        runs={runCandidates}
        onViewRun={(runId) => navigate({ name: "run-detail", runId })}
      />

      {matchingRunErrors.length > 0 ? (
        <Notice tone="warning" title="Run link is incomplete" className="mb-6">
          {matchingRunErrors.join(" ")}
        </Notice>
      ) : null}

      {riskBlockedCount > 0 ? (
        <Notice
          tone="danger"
          title={`${riskBlockedCount} blocked action${riskBlockedCount === 1 ? "" : "s"}`}
          className="mb-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>These actions cannot be applied until the underlying issue is resolved.</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setActionStatus("blocked")
                setViewMode("table")
              }}
            >
              View blocked actions
            </Button>
          </div>
        </Notice>
      ) : null}

      {actionFacetErrors.length > 0 ? (
        <Notice tone="warning" title="Plan action summary is incomplete" className="mb-6">
          {actionFacetErrors.join(" ")}
        </Notice>
      ) : null}

      <section
        aria-label="Plan risk summary"
        className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4"
      >
        <MetricCard label="Recorded actions" value={recordedActionCount} tone="neutral" />
        <MetricCard
          label="Blocked"
          value={riskBlockedCount}
          tone={riskBlockedCount > 0 ? "danger" : "neutral"}
        />
        <MetricCard
          label="Target collisions"
          value={collisionCount}
          tone={collisionCount > 0 ? "danger" : "neutral"}
          hint="Targets written by 2+ actions"
        />
        <MetricCard
          label="Unknown metadata"
          value={unknownMetadataCount}
          tone={unknownMetadataCount > 0 ? "warning" : "neutral"}
          hint="Missing required tags"
        />
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

      <PlanActionsPanel
        planId={planId}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        actionStatus={actionStatus}
        onActionStatusChange={setActionStatus}
      />
    </>
  )
}
