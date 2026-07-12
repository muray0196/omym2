/*
Summary: Renders the Plan actions panel with grouped, table, and diff views.
Why: Lets a Plan with thousands of actions read as meaningful library operations.
*/

"use client"

import { ChevronDown, ChevronRight, FileDiff, Hash, ListTree, Table2 } from "lucide-react"
import { useCallback, useEffect, useId, useState } from "react"
import { getPlanActionsPage, getPlanFacets, getPlanGroups } from "../api-client"
import { BrowseFilters, countedFacetOptions, SEARCH_DEBOUNCE_MS } from "../browse-filters"
import { useDebouncedValue } from "../use-debounced-value"
import { cn, describeBlockReason, truncateMiddle } from "../lib"
import type {
  FacetValue,
  PlanAction,
  PlanActionReason,
  PlanActionStatus,
  PlanActionType,
  PlanGroupBy,
  PlanGroupCount,
} from "../types"
import { usePagedList, type PagedListState } from "../use-paged-list"
import { Select } from "../forms"
import {
  Button,
  DataTable,
  EmptyState,
  Mono,
  Notice,
  Panel,
  PathArrow,
  SegmentedControl,
  StatusBadge,
  truncateLabel,
  type Column,
  type SegmentedOption,
} from "../primitives"

const PLAN_ACTION_PAGE_LIMIT = 100
const PLAN_GROUP_PAGE_LIMIT = 50
const GROUP_ACTION_PAGE_LIMIT = 50

export type PlanViewMode = "grouped" | "table" | "diff"

const VIEW_MODE_OPTIONS: SegmentedOption<PlanViewMode>[] = [
  { value: "grouped", label: "Grouped", icon: ListTree },
  { value: "table", label: "Table", icon: Table2 },
  { value: "diff", label: "Diff", icon: FileDiff },
]

const GROUP_BY_OPTIONS: { value: PlanGroupBy; label: string }[] = [
  { value: "target_directory", label: "Target directory" },
  { value: "source_directory", label: "Source directory" },
  { value: "artist_album", label: "Album artist / album" },
  { value: "action_type", label: "Action type" },
  { value: "status", label: "Status" },
  { value: "block_reason", label: "Block reason" },
  { value: "extension", label: "File extension" },
]

const ACTION_FILTERS: { value: PlanActionStatus | "all"; label: string }[] = [
  { value: "all", label: "All actions" },
  { value: "planned", label: "Planned" },
  { value: "blocked", label: "Blocked" },
  { value: "applied", label: "Applied" },
  { value: "failed", label: "Failed" },
]

const ACTION_TYPE_FILTERS: { value: PlanActionType | "all"; label: string }[] = [
  { value: "all", label: "All action types" },
  { value: "move", label: "Move" },
  { value: "skip", label: "Skip" },
  { value: "refresh_metadata", label: "Refresh metadata" },
]

const REASON_FILTERS: { value: PlanActionReason | "all"; label: string }[] = [
  { value: "all", label: "All reasons" },
  { value: "target_exists", label: "Target exists" },
  { value: "missing_required_metadata", label: "Missing required metadata" },
  { value: "invalid_path", label: "Invalid path" },
  { value: "source_missing", label: "Source missing" },
  { value: "source_changed", label: "Source changed" },
  { value: "duplicate_hash", label: "Duplicate hash" },
]

interface PlanActionFilters {
  query: string
  status: PlanActionStatus | "all"
  actionType: PlanActionType | "all"
  reason: PlanActionReason | "all"
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

/**
 * Humanized block reason. Unknown reasons fall back to the raw snake_case
 * string — keep the Mono treatment for those; humanized text reads as a
 * sentence.
 */
function ReasonText({ reason, className }: { reason: string; className?: string }) {
  const described = describeBlockReason(reason)
  return described === reason ? (
    <Mono className={cn("text-warning", className)} title={reason}>
      {reason}
    </Mono>
  ) : (
    <span className={cn("text-warning", className)} title={reason}>
      {described}
    </span>
  )
}

/** Shared "N of M loaded" footer for the non-table paged lists. */
function LoadMoreFooter({
  shown,
  total,
  hasMore,
  loading,
  onLoadMore,
  noun,
  className,
}: {
  shown: number
  total: number | null
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
  noun: string
  className?: string
}) {
  const cappedShown = total === null ? shown : Math.min(shown, total)
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 bg-surface-elevated px-3 py-2.5",
        className,
      )}
    >
      <span className="text-xs tabular-nums text-mute">
        {total === null
          ? `${cappedShown} ${noun}${cappedShown === 1 ? "" : "s"} loaded`
          : `${cappedShown} of ${total} ${noun}${total === 1 ? "" : "s"} loaded`}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={!hasMore || loading}
        onClick={onLoadMore}
      >
        <ChevronDown className="size-4" aria-hidden="true" />
        {loading ? "Loading..." : hasMore ? "Load more" : `All ${noun}s loaded`}
      </Button>
    </div>
  )
}

/**
 * The Actions panel: a Grouped/Table/Diff mode switcher in the header plus
 * the matching control (Group by in Grouped mode, status filter otherwise).
 * View mode and status live in the parent so the blocked-actions notice can
 * jump straight to the blocked table.
 */
export function PlanActionsPanel({
  planId,
  viewMode,
  onViewModeChange,
  actionStatus,
  onActionStatusChange,
}: {
  planId: string
  viewMode: PlanViewMode
  onViewModeChange: (mode: PlanViewMode) => void
  actionStatus: PlanActionStatus | "all"
  onActionStatusChange: (status: PlanActionStatus | "all") => void
}) {
  const [groupBy, setGroupBy] = useState<PlanGroupBy>("artist_album")
  const [query, setQuery] = useState("")
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS)
  const [actionType, setActionType] = useState<PlanActionType | "all">("all")
  const [reason, setReason] = useState<PlanActionReason | "all">("all")
  const [facets, setFacets] = useState<Record<string, FacetValue[]>>({})
  const [facetTotal, setFacetTotal] = useState<number | null>(null)
  const [facetErrors, setFacetErrors] = useState<string[]>([])
  const filters: PlanActionFilters = {
    query: debouncedQuery,
    status: actionStatus,
    actionType,
    reason,
  }

  useEffect(() => {
    let cancelled = false
    getPlanFacets(planId, {
      query: debouncedQuery.trim() || undefined,
      status: actionStatus,
      actionType,
      reason,
    })
      .then((response) => {
        if (cancelled) return
        setFacets(response.facets)
        setFacetTotal(response.total)
        setFacetErrors(response.errors)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setFacets({})
        setFacetTotal(null)
        setFacetErrors([errorMessage(error, "Plan action facets failed to load.")])
      })
    return () => {
      cancelled = true
    }
  }, [actionStatus, actionType, debouncedQuery, planId, reason])

  return (
    <Panel
      title="Actions"
      icon={FileDiff}
      bodyClassName="flex flex-col gap-4"
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <SegmentedControl
            ariaLabel="Actions view mode"
            size="sm"
            options={VIEW_MODE_OPTIONS}
            value={viewMode}
            onChange={onViewModeChange}
          />
          {viewMode === "grouped" ? (
            <div className="w-48">
              <Select
                aria-label="Group by"
                options={GROUP_BY_OPTIONS}
                value={groupBy}
                onChange={(event) => setGroupBy(event.target.value as PlanGroupBy)}
              />
            </div>
          ) : null}
        </div>
      }
    >
      <BrowseFilters
        query={query}
        onQueryChange={setQuery}
        searchHelp="Match action or track IDs, recorded paths, or recorded hashes."
        searchPlaceholder="Search Plan actions…"
        total={facetTotal}
        facets={[
          {
            key: "status",
            label: "Status",
            value: actionStatus,
            options: countedFacetOptions(ACTION_FILTERS, facets.status),
            onChange: (value) => onActionStatusChange(value as PlanActionStatus | "all"),
          },
          {
            key: "action_type",
            label: "Action type",
            value: actionType,
            options: countedFacetOptions(ACTION_TYPE_FILTERS, facets.action_type),
            onChange: (value) => setActionType(value as PlanActionType | "all"),
          },
          {
            key: "reason",
            label: "Reason",
            value: reason,
            options: countedFacetOptions(REASON_FILTERS, facets.reason),
            onChange: (value) => setReason(value as PlanActionReason | "all"),
          },
        ]}
      />
      {facetErrors.length > 0 ? (
        <Notice tone="warning" title="Plan action facets are incomplete">
          {facetErrors.join(" ")}
        </Notice>
      ) : null}
      {viewMode === "grouped" ? (
        // Keyed by groupBy so switching keys resets expansion and paging state.
        <PlanActionGroups key={groupBy} planId={planId} groupBy={groupBy} filters={filters} />
      ) : (
        <PlanActionsFlat planId={planId} mode={viewMode} filters={filters} />
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* Grouped view                                                        */
/* ------------------------------------------------------------------ */

const PATH_LIKE_GROUPS: ReadonlySet<PlanGroupBy> = new Set([
  "target_directory",
  "source_directory",
  "extension",
])

function groupLabel(groupBy: PlanGroupBy, group: PlanGroupCount): React.ReactNode {
  if (PATH_LIKE_GROUPS.has(groupBy)) {
    return (
      <Mono className="truncate text-ink" title={group.label}>
        {group.label}
      </Mono>
    )
  }
  if (groupBy === "block_reason") {
    return (
      <span className="truncate text-ink" title={group.key}>
        {describeBlockReason(group.key)}
      </span>
    )
  }
  if (groupBy === "action_type" || groupBy === "status") {
    return <span className="truncate text-ink">{truncateLabel(group.label)}</span>
  }
  return (
    <span className="truncate font-medium text-ink" title={group.label}>
      {group.label}
    </span>
  )
}

function PlanActionGroups({
  planId,
  groupBy,
  filters,
}: {
  planId: string
  groupBy: PlanGroupBy
  filters: PlanActionFilters
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const loadGroupsPage = useCallback(
    (cursor?: string) =>
      getPlanGroups(planId, {
        groupBy,
        cursor,
        limit: PLAN_GROUP_PAGE_LIMIT,
        query: filters.query.trim() || undefined,
        status: filters.status,
        actionType: filters.actionType,
        reason: filters.reason,
      }),
    [filters.actionType, filters.query, filters.reason, filters.status, groupBy, planId],
  )
  const groupsPage = usePagedList<PlanGroupCount>({
    errorMessage: "Plan action groups failed to load.",
    loadPage: loadGroupsPage,
  })
  const groups = groupsPage.items

  return (
    <div className="flex flex-col gap-4">
      {groupsPage.errors.length > 0 ? (
        <Notice tone="warning" title="Plan action groups are incomplete">
          {groupsPage.errors.join(" ")}
        </Notice>
      ) : null}
      {groups.length === 0 ? (
        <EmptyState
          icon={ListTree}
          title={groupsPage.loaded ? "No groups to show." : "Loading groups..."}
          description={
            groupsPage.loaded
              ? "Actions without a value for this grouping key are not grouped."
              : undefined
          }
        />
      ) : (
        <div className="overflow-hidden rounded-md border border-hairline">
          <ul className="flex flex-col">
            {groups.map((group) => (
              <PlanGroupRow
                key={group.key}
                planId={planId}
                groupBy={groupBy}
                group={group}
                filters={filters}
                expanded={expandedKey === group.key}
                onToggle={() =>
                  setExpandedKey((current) => (current === group.key ? null : group.key))
                }
              />
            ))}
          </ul>
          <LoadMoreFooter
            className="border-t border-hairline"
            shown={groups.length}
            total={groupsPage.page?.total ?? groups.length}
            hasMore={groupsPage.hasMore}
            loading={groupsPage.loadingMore}
            onLoadMore={groupsPage.loadMore}
            noun="group"
          />
        </div>
      )}
    </div>
  )
}

function PlanGroupRow({
  planId,
  groupBy,
  group,
  filters,
  expanded,
  onToggle,
}: {
  planId: string
  groupBy: PlanGroupBy
  group: PlanGroupCount
  filters: PlanActionFilters
  expanded: boolean
  onToggle: () => void
}) {
  const contentId = useId()
  const showTargetHint =
    groupBy === "artist_album" && group.key !== "(unknown)" && group.key !== "(root)"
  // For block_reason groups the primary label already is the humanized
  // reason, so repeating top_reason underneath would be redundant.
  const topReason = groupBy === "block_reason" ? null : group.top_reason
  return (
    <li className="border-b border-hairline last:border-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={onToggle}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors hover:bg-surface-card/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
      >
        <ChevronRight
          className={cn("size-4 shrink-0 text-mute transition-transform", expanded && "rotate-90")}
          aria-hidden="true"
        />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          {groupLabel(groupBy, group)}
          {showTargetHint ? (
            <Mono className="truncate text-xs text-mute" title={`${group.key}/`}>
              target: {group.key}/
            </Mono>
          ) : null}
          {topReason ? (
            <span className="truncate text-xs text-warning">
              main reason: <ReasonText reason={topReason} />
            </span>
          ) : null}
        </span>
        <span
          className={cn(
            "shrink-0 rounded-md px-2 py-0.5 text-xs font-medium",
            group.blocked_count > 0 ? "bg-danger-muted text-danger" : "text-mute",
          )}
        >
          {group.blocked_count} blocked
        </span>
        <span className="shrink-0 tabular-nums text-mute">
          {group.count} action{group.count === 1 ? "" : "s"}
        </span>
      </button>
      {expanded ? (
        <div
          id={contentId}
          className="border-t border-hairline bg-surface-canvas/60 py-1 pl-9 pr-3"
        >
          <PlanGroupActionList
            planId={planId}
            groupBy={groupBy}
            groupKey={group.key}
            filters={filters}
          />
        </div>
      ) : null}
    </li>
  )
}

function PlanGroupActionList({
  planId,
  groupBy,
  groupKey,
  filters,
}: {
  planId: string
  groupBy: PlanGroupBy
  groupKey: string
  filters: PlanActionFilters
}) {
  const loadPage = useCallback(
    (cursor?: string) =>
      getPlanActionsPage(planId, {
        cursor,
        limit: GROUP_ACTION_PAGE_LIMIT,
        groupBy,
        groupKey,
        query: filters.query.trim() || undefined,
        status: filters.status,
        actionType: filters.actionType,
        reason: filters.reason,
      }),
    [filters.actionType, filters.query, filters.reason, filters.status, groupBy, groupKey, planId],
  )
  const actionsPage = usePagedList<PlanAction>({
    errorMessage: "Group actions failed to load.",
    loadPage,
  })
  return (
    <div className="flex flex-col">
      {actionsPage.errors.length > 0 ? (
        <Notice tone="warning" title="Group actions are incomplete" className="my-2">
          {actionsPage.errors.join(" ")}
        </Notice>
      ) : null}
      {actionsPage.items.length === 0 ? (
        <p className="py-2 text-sm text-mute">
          {actionsPage.loaded ? "No actions in this group." : "Loading actions..."}
        </p>
      ) : (
        <ul className="flex flex-col">
          {actionsPage.items.map((action) => (
            <li
              key={action.action_id}
              className="flex items-start gap-2.5 border-b border-hairline-soft py-2 last:border-0"
            >
              <StatusBadge status={action.status} iconOnly className="mt-0.5" />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <PathArrow
                  source={action.source_path ?? ""}
                  target={action.target_path ?? ""}
                  max={40}
                />
                {action.reason ? <ReasonText reason={action.reason} className="text-xs" /> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      {actionsPage.hasMore || actionsPage.loadingMore ? (
        <LoadMoreFooter
          className="rounded-md"
          shown={actionsPage.items.length}
          total={actionsPage.page?.total ?? actionsPage.items.length}
          hasMore={actionsPage.hasMore}
          loading={actionsPage.loadingMore}
          onLoadMore={actionsPage.loadMore}
          noun="action"
        />
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Flat views (table + diff share one paged action list)               */
/* ------------------------------------------------------------------ */

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

/**
 * Table and Diff render the same status-filtered paged action list, so one
 * component owns the fetch: switching between the two modes reuses the
 * already-loaded pages instead of refetching.
 */
function PlanActionsFlat({
  planId,
  mode,
  filters,
}: {
  planId: string
  mode: "table" | "diff"
  filters: PlanActionFilters
}) {
  const loadActionsPage = useCallback(
    (cursor?: string) =>
      getPlanActionsPage(planId, {
        cursor,
        limit: PLAN_ACTION_PAGE_LIMIT,
        query: filters.query.trim() || undefined,
        status: filters.status,
        actionType: filters.actionType,
        reason: filters.reason,
      }),
    [filters.actionType, filters.query, filters.reason, filters.status, planId],
  )
  const actionsPage = usePagedList<PlanAction>({
    errorMessage: "Plan actions failed to load.",
    loadPage: loadActionsPage,
  })

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
      cell: (action) =>
        action.reason ? (
          <ReasonText reason={action.reason} />
        ) : (
          <span className="text-mute">—</span>
        ),
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
      {actionsPage.errors.length > 0 ? (
        <Notice tone="warning" title="Plan actions are incomplete" className="mb-4">
          {actionsPage.errors.join(" ")}
        </Notice>
      ) : null}
      {mode === "table" ? (
        <DataTable
          columns={columns}
          rows={actionsPage.items}
          getRowKey={(action) => action.action_id}
          rowIsActive={(action) => action.status === "blocked" || action.status === "failed"}
          caption="Plan actions"
          empty={
            <EmptyState
              icon={FileDiff}
              title={actionsPage.loaded ? "No actions match your filters." : "Loading actions..."}
            />
          }
          loadMore={{
            hasMore: actionsPage.hasMore,
            loading: actionsPage.loadingMore,
            onLoadMore: actionsPage.loadMore,
            total: actionsPage.page?.total ?? actionsPage.items.length,
          }}
        />
      ) : (
        <PlanActionsDiff actionsPage={actionsPage} />
      )}
    </>
  )
}

/**
 * Rename-diff reading of the action list: a `-` source line and `+` target
 * line per action. Actions without a target keep the `-` line and swap the
 * `+` line for a muted annotation (reason or action type), because nothing
 * is written for them.
 */
function PlanActionsDiff({ actionsPage }: { actionsPage: PagedListState<PlanAction> }) {
  const actions = actionsPage.items
  if (actions.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState
          icon={FileDiff}
          title={actionsPage.loaded ? "No actions match this filter." : "Loading actions..."}
        />
        {actionsPage.hasMore || actionsPage.loadingMore ? (
          <LoadMoreFooter
            className="rounded-md border border-hairline"
            shown={actions.length}
            total={actionsPage.page?.total ?? actions.length}
            hasMore={actionsPage.hasMore}
            loading={actionsPage.loadingMore}
            onLoadMore={actionsPage.loadMore}
            noun="action"
          />
        ) : null}
      </div>
    )
  }
  return (
    <div className="overflow-hidden rounded-md border border-hairline">
      <ol aria-label="Plan actions as rename diff" className="flex flex-col">
        {actions.map((action) => {
          const highlighted = action.status === "blocked" || action.status === "failed"
          return (
            <li
              key={action.action_id}
              className={cn(
                "flex flex-col gap-1 border-b border-hairline px-3 py-2.5 last:border-0",
                highlighted && "bg-accent",
              )}
            >
              <Mono
                className="block truncate rounded-sm bg-danger-muted px-2 py-1 text-danger"
                title={action.source_path ?? undefined}
              >
                - {action.source_path ?? "—"}
              </Mono>
              {action.target_path !== null ? (
                <Mono
                  className="block truncate rounded-sm bg-success-muted px-2 py-1 text-success"
                  title={action.target_path}
                >
                  + {action.target_path}
                </Mono>
              ) : (
                <span className="px-2 py-0.5 text-xs text-mute">
                  No target —{" "}
                  {action.reason
                    ? describeBlockReason(action.reason)
                    : truncateLabel(action.action_type)}
                </span>
              )}
              {action.reason && action.target_path !== null ? (
                <ReasonText reason={action.reason} className="px-2 text-xs" />
              ) : null}
            </li>
          )
        })}
      </ol>
      <LoadMoreFooter
        className="border-t border-hairline"
        shown={actions.length}
        total={actionsPage.page?.total ?? actions.length}
        hasMore={actionsPage.hasMore}
        loading={actionsPage.loadingMore}
        onLoadMore={actionsPage.loadMore}
        noun="action"
      />
    </div>
  )
}
