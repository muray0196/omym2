/*
Summary: Renders paged Plan browsing and Plan creation controls.
Why: Supports reviewing large Plan histories without full-list API reads.
*/

"use client"

import { ClipboardList, FolderInput, FolderTree, Plus, RefreshCcw, Table2 } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
import { getPlansPage } from "../api-client"
import { useApp } from "../app-context"
import { diffConfig, formatTimestamp, truncateMiddle } from "../lib"
import type { PlanCreateResult, PlanStatus, PlanSummary, PlanType } from "../types"
import { usePagedList } from "../use-paged-list"
import { Field, Select, TextInput, Toggle } from "../forms"
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
  type Column,
} from "../primitives"
import { PageHeading } from "./page-heading"

const STATUS_OPTIONS: { value: PlanStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "ready", label: "Ready" },
  { value: "applying", label: "Applying" },
  { value: "applied", label: "Applied" },
  { value: "partial_failed", label: "Partial failed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "expired", label: "Expired" },
]

const TYPE_OPTIONS: { value: PlanType | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "add", label: "Add" },
  { value: "organize", label: "Organize" },
  { value: "refresh", label: "Refresh" },
  { value: "undo", label: "Undo" },
]

const LIMIT_OPTIONS = [
  { value: "10", label: "10 / page" },
  { value: "25", label: "25 / page" },
  { value: "50", label: "50 / page" },
  { value: "100", label: "100 / page" },
]

type CreateMode = "add" | "organize" | "refresh"

const CREATE_MODES: {
  value: CreateMode
  label: string
  icon: typeof Plus
}[] = [
  { value: "add", label: "Add", icon: FolderInput },
  { value: "organize", label: "Organize", icon: FolderTree },
  { value: "refresh", label: "Refresh", icon: RefreshCcw },
]

function summaryNumber(plan: PlanSummary, key: string): number {
  const raw = plan.summary[key]
  if (!raw) return 0
  const parsed = Number.parseInt(raw, 10)
  return Number.isNaN(parsed) ? 0 : parsed
}

function optionalPath(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === "" ? null : trimmed
}

function CreatePlanPanel() {
  const {
    createAddPlan,
    createOrganizePlan,
    createRefreshPlan,
    draftConfig,
    navigate,
    savedConfig,
  } = useApp()
  const [mode, setMode] = useState<CreateMode>("add")
  const [sourcePath, setSourcePath] = useState("")
  const [libraryRoot, setLibraryRoot] = useState("")
  const [targetPath, setTargetPath] = useState("")
  const [includeAll, setIncludeAll] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [result, setResult] = useState<PlanCreateResult | null>(null)

  const hasUnsavedSettings = diffConfig(savedConfig, draftConfig).length > 0
  const refreshNeedsTarget = mode === "refresh" && !includeAll && optionalPath(targetPath) === null
  const disabled = hasUnsavedSettings || refreshNeedsTarget || isCreating

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (disabled) return
    setIsCreating(true)
    try {
      const createResult =
        mode === "add"
          ? await createAddPlan(optionalPath(sourcePath))
          : mode === "organize"
            ? await createOrganizePlan(optionalPath(libraryRoot))
            : await createRefreshPlan(optionalPath(targetPath), includeAll)
      setResult(createResult)
      if (createResult.detail) {
        navigate({ name: "plan-detail", planId: createResult.detail.plan.plan_id })
      }
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <Panel
      title="Create Plan"
      icon={Plus}
      bodyClassName="flex flex-col gap-4"
      actions={
        <div className="flex items-center gap-1.5 rounded-xs border border-hairline bg-surface-elevated px-2 py-1 text-xs text-on-dark-mute">
          <span>album_year_resolution</span>
          <Mono className="text-on-dark">{savedConfig.metadata.album_year_resolution}</Mono>
        </div>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <SegmentedControl
          ariaLabel="Plan type"
          options={CREATE_MODES}
          value={mode}
          onChange={setMode}
        />

        {mode === "add" ? (
          <Field label="Source path" help="Blank uses the saved Incoming path.">
            {(id) => (
              <TextInput
                id={id}
                mono
                placeholder={savedConfig.paths.incoming ?? "/music/incoming"}
                value={sourcePath}
                onChange={(event) => setSourcePath(event.target.value)}
              />
            )}
          </Field>
        ) : null}

        {mode === "organize" ? (
          <Field label="Library root" help="Blank uses the saved Library path.">
            {(id) => (
              <TextInput
                id={id}
                mono
                placeholder={savedConfig.paths.library ?? "/music/library"}
                value={libraryRoot}
                onChange={(event) => setLibraryRoot(event.target.value)}
              />
            )}
          </Field>
        ) : null}

        {mode === "refresh" ? (
          <div className="grid gap-3">
            <Toggle
              checked={includeAll}
              onChange={setIncludeAll}
              label="All managed tracks"
              help="Create refresh actions for every active Track."
            />
            <Field label="Target path" help="Required unless all managed tracks is enabled.">
              {(id) => (
                <TextInput
                  id={id}
                  mono
                  disabled={includeAll}
                  placeholder="Artist/2026_Album/1-02_Title.flac"
                  value={targetPath}
                  onChange={(event) => setTargetPath(event.target.value)}
                />
              )}
            </Field>
          </div>
        ) : null}

        {hasUnsavedSettings ? (
          <Notice tone="warning" title="Save settings first">
            Plan creation reads persisted settings.
          </Notice>
        ) : null}

        {result?.errors.length ? (
          <Notice tone="danger" title="Plan creation failed">
            {result.errors.join(" ")}
          </Notice>
        ) : null}

        {result?.registration && !result.detail ? (
          <Notice tone="success" title="Library registered — no plan needed">
            <p className="mb-2">
              This registration did not produce a Plan; there is nothing to apply.
            </p>
            <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-3">
              <div>
                <dt className="text-xs uppercase tracking-wide text-mute">Root path</dt>
                <dd>
                  <Mono className="text-ink" title={result.registration.library.root_path}>
                    {result.registration.library.root_path}
                  </Mono>
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-mute">Status</dt>
                <dd>
                  <StatusBadge status={result.registration.library.status} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-mute">Tracks</dt>
                <dd className="tabular-nums">{result.registration.track_count}</dd>
              </div>
            </dl>
          </Notice>
        ) : null}

        <Button type="submit" disabled={disabled}>
          <Plus className="size-4" aria-hidden="true" />
          {isCreating ? "Creating..." : "Create Plan"}
        </Button>
      </form>
    </Panel>
  )
}

export function PlansScreen() {
  const { navigate } = useApp()
  const [status, setStatus] = useState<PlanStatus | "all">("all")
  const [planType, setPlanType] = useState<PlanType | "all">("all")
  const [limit, setLimit] = useState(25)

  const loadPlansPage = useCallback(
    (cursor?: string) =>
      getPlansPage({
        cursor,
        limit,
        status,
        type: planType,
      }),
    [limit, planType, status],
  )
  const plansPage = usePagedList({
    errorMessage: "Plans failed to load.",
    loadPage: loadPlansPage,
  })

  const counts = useMemo(() => {
    return plansPage.items.reduce(
      (acc, plan) => {
        acc.total += 1
        acc[plan.status] = (acc[plan.status] ?? 0) + 1
        return acc
      },
      { total: 0 } as Record<string, number>,
    )
  }, [plansPage.items])

  const matchingTotal = plansPage.page?.total ?? plansPage.items.length

  const columns: Column<PlanSummary>[] = [
    {
      key: "plan_id",
      header: "Plan ID",
      cell: (plan) => (
        <Mono className="text-ink" title={plan.plan_id}>
          {truncateMiddle(plan.plan_id, 22)}
        </Mono>
      ),
    },
    {
      key: "type",
      header: "Type",
      cell: (plan) => <span className="font-medium">{plan.plan_type}</span>,
      className: "w-28",
    },
    {
      key: "status",
      header: "Status",
      cell: (plan) => <StatusBadge status={plan.status} iconOnly />,
      className: "w-16 text-center",
    },
    {
      key: "actions",
      header: "Actions",
      cell: (plan) => (
        <span className="tabular-nums text-mute">{summaryNumber(plan, "action_count")}</span>
      ),
      className: "w-20",
    },
    {
      key: "blocked",
      header: "Blocked",
      cell: (plan) => (
        <span className="tabular-nums text-mute">{summaryNumber(plan, "blocked_actions")}</span>
      ),
      className: "w-20",
    },
    {
      key: "created_at",
      header: "Created",
      cell: (plan) => (
        <span className="whitespace-nowrap text-mute">{formatTimestamp(plan.created_at)}</span>
      ),
      className: "w-40",
    },
  ]

  return (
    <>
      <PageHeading title="Plans" description="Review planned target paths before CLI apply." />

      <section
        aria-label="Plan summary"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      >
        <MetricCard label="Matching" value={matchingTotal} tone="neutral" />
        <MetricCard label="Loaded" value={counts.total ?? 0} tone="neutral" />
        <MetricCard label="Loaded ready" value={counts.ready ?? 0} tone="info" />
        <MetricCard label="Loaded applied" value={counts.applied ?? 0} tone="success" />
        <MetricCard label="Loaded failed" value={counts.failed ?? 0} tone="danger" />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <Panel title="Plan review" icon={ClipboardList} bodyClassName="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Status">
              {(id) => (
                <Select
                  id={id}
                  options={STATUS_OPTIONS}
                  value={status}
                  onChange={(event) => setStatus(event.target.value as PlanStatus | "all")}
                />
              )}
            </Field>
            <Field label="Type">
              {(id) => (
                <Select
                  id={id}
                  options={TYPE_OPTIONS}
                  value={planType}
                  onChange={(event) => setPlanType(event.target.value as PlanType | "all")}
                />
              )}
            </Field>
            <Field label="Limit">
              {(id) => (
                <Select
                  id={id}
                  options={LIMIT_OPTIONS}
                  value={String(limit)}
                  onChange={(event) => setLimit(Number.parseInt(event.target.value, 10))}
                />
              )}
            </Field>
          </div>

          {plansPage.errors.length > 0 ? (
            <Notice tone="warning" title="Plan data is incomplete">
              {plansPage.errors.join(" ")}
            </Notice>
          ) : null}

          <DataTable
            columns={columns}
            rows={plansPage.items}
            getRowKey={(plan) => plan.plan_id}
            onRowClick={(plan) => navigate({ name: "plan-detail", planId: plan.plan_id })}
            caption="Plans"
            empty={
              <EmptyState
                icon={Table2}
                title={plansPage.loaded ? "No plans match these filters." : "Loading plans..."}
                description={
                  plansPage.loaded
                    ? "Adjust filters or create a new Plan."
                    : "Plans will appear here once they are loaded."
                }
              />
            }
            loadMore={{
              hasMore: plansPage.hasMore,
              loading: plansPage.loadingMore,
              onLoadMore: plansPage.loadMore,
              total: matchingTotal,
            }}
          />
        </Panel>

        <CreatePlanPanel />
      </div>
    </>
  )
}
