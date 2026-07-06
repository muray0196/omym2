"use client"

import {
  ClipboardList,
  FolderInput,
  FolderTree,
  Plus,
  RefreshCcw,
  Search,
  Table2,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useApp, type PlanFilters } from "../app-context"
import { cn, diffConfig, formatTimestamp, truncateMiddle } from "../lib"
import type { PlanCreateResult, PlanStatus, PlanSummary, PlanType } from "../types"
import { Field, Select, TextInput, Toggle } from "../forms"
import {
  Button,
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
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
  { value: "10", label: "10 newest" },
  { value: "25", label: "25 newest" },
  { value: "50", label: "50 newest" },
  { value: "100", label: "100 newest" },
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

function CreateModeButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean
  icon: typeof Plus
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex min-h-9 items-center justify-center gap-1.5 rounded px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </button>
  )
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
        <div className="rounded-md border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          <span className="mr-1">album_year_resolution</span>
          <Mono className="text-foreground">{savedConfig.metadata.album_year_resolution}</Mono>
        </div>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div
          role="group"
          aria-label="Plan type"
          className="grid rounded-md border border-border bg-muted p-0.5 sm:grid-cols-3"
        >
          {CREATE_MODES.map((entry) => (
            <CreateModeButton
              key={entry.value}
              active={mode === entry.value}
              icon={entry.icon}
              label={entry.label}
              onClick={() => setMode(entry.value)}
            />
          ))}
        </div>

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
          <Notice tone="success" title="Library registered">
            {result.registration.track_count} tracks recorded.
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
  const { loadPlans, navigate, planErrors, plans, plansLoaded } = useApp()
  const [status, setStatus] = useState<PlanStatus | "all">("all")
  const [planType, setPlanType] = useState<PlanType | "all">("all")
  const [limit, setLimit] = useState(25)
  const [query, setQuery] = useState("")

  useEffect(() => {
    const filters: PlanFilters = { status, type: planType, limit }
    void loadPlans(filters)
  }, [limit, loadPlans, planType, status])

  const counts = useMemo(() => {
    return plans.reduce(
      (acc, plan) => {
        acc.total += 1
        acc[plan.status] = (acc[plan.status] ?? 0) + 1
        return acc
      },
      { total: 0 } as Record<string, number>,
    )
  }, [plans])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return plans
    return plans.filter((plan) => {
      return (
        plan.plan_id.toLowerCase().includes(needle) ||
        plan.library_id.toLowerCase().includes(needle) ||
        plan.plan_type.toLowerCase().includes(needle) ||
        plan.status.toLowerCase().includes(needle)
      )
    })
  }, [plans, query])

  const columns: Column<PlanSummary>[] = [
    {
      key: "plan_id",
      header: "Plan ID",
      cell: (plan) => (
        <Mono className="text-foreground" title={plan.plan_id}>
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
        <span className="tabular-nums text-muted-foreground">
          {summaryNumber(plan, "action_count")}
        </span>
      ),
      className: "w-20",
    },
    {
      key: "blocked",
      header: "Blocked",
      cell: (plan) => (
        <span className="tabular-nums text-muted-foreground">
          {summaryNumber(plan, "blocked_actions")}
        </span>
      ),
      className: "w-20",
    },
    {
      key: "created_at",
      header: "Created",
      cell: (plan) => (
        <span className="whitespace-nowrap text-muted-foreground">
          {formatTimestamp(plan.created_at)}
        </span>
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
        <MetricCard label="Total" value={counts.total ?? 0} tone="neutral" />
        <MetricCard label="Ready" value={counts.ready ?? 0} tone="info" />
        <MetricCard label="Applied" value={counts.applied ?? 0} tone="success" />
        <MetricCard label="Partial failed" value={counts.partial_failed ?? 0} tone="warning" />
        <MetricCard label="Failed" value={counts.failed ?? 0} tone="danger" />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <Panel title="Plan review" icon={ClipboardList} bodyClassName="flex flex-col gap-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_10rem_10rem_8rem]">
            <Field label="Search">
              {(id) => (
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <TextInput
                    id={id}
                    className="pl-8"
                    placeholder="Search plans..."
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
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

          {planErrors.length > 0 ? (
            <Notice tone="warning" title="Plan data is incomplete">
              {planErrors.join(" ")}
            </Notice>
          ) : null}

          <DataTable
            columns={columns}
            rows={filtered}
            getRowKey={(plan) => plan.plan_id}
            onRowClick={(plan) => navigate({ name: "plan-detail", planId: plan.plan_id })}
            caption="Plans"
            empty={
              <EmptyState
                icon={Table2}
                title={plansLoaded ? "No plans match your filters." : "Loading plans..."}
                description={
                  plansLoaded
                    ? "Adjust filters or create a new Plan."
                    : "Plans will appear here once they are loaded."
                }
              />
            }
          />
        </Panel>

        <CreatePlanPanel />
      </div>
    </>
  )
}
