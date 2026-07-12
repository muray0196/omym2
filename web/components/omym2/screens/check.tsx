/*
Summary: Renders grouped Check triage and detailed issue browsing.
Why: Lets large-library diagnostics reveal concentrated problems before individual rows.
*/

"use client"

import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleX,
  Info,
  ListTree,
  ShieldCheck,
  Table2,
} from "lucide-react"
import { useCallback, useEffect, useId, useMemo, useState } from "react"
import { getCheckFacets, getCheckGroups, getCheckPage } from "../api-client"
import { BrowseFilters, countedFacetOptions, SEARCH_DEBOUNCE_MS } from "../browse-filters"
import { useDebouncedValue } from "../use-debounced-value"
import { cn, severityForIssue, truncateMiddle } from "../lib"
import type {
  CheckGroupBy,
  CheckGroupCount,
  CheckIssue,
  CheckIssueType,
  FacetValue,
  IssueSeverity,
} from "../types"
import { usePagedList } from "../use-paged-list"
import {
  Button,
  CopyButton,
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  SegmentedControl,
  StatusBadge,
  truncateLabel,
  type Column,
  type SegmentedOption,
} from "../primitives"
import { CliCommand } from "../widgets"
import { Select } from "../forms"

import { PageHeading } from "./page-heading"

const ISSUE_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All issue types" },
  { value: "db_file_missing", label: "DB file missing" },
  { value: "unmanaged_file_exists", label: "Unmanaged file exists" },
  { value: "content_hash_changed", label: "Content hash changed" },
  { value: "metadata_hash_changed", label: "Metadata hash changed" },
  { value: "current_path_differs_from_canonical_path", label: "Path mismatch" },
  { value: "duplicate_candidate", label: "Duplicate candidate" },
  { value: "plan_source_changed", label: "Plan source changed" },
  { value: "pending_file_event_exists", label: "Pending file event" },
  { value: "library_unregistered", label: "Library unregistered" },
  { value: "library_stale", label: "Library stale" },
  { value: "library_blocked", label: "Library blocked" },
]

const CHECK_TABLE_PAGE_LIMIT = 100
const CHECK_GROUP_PAGE_LIMIT = 50
const CHECK_EXAMPLE_PAGE_LIMIT = 3
const CHECK_GROUP_ISSUE_PAGE_LIMIT = 50

const MISSING_TYPES: CheckIssueType[] = ["db_file_missing"]
const UNMANAGED_TYPES: CheckIssueType[] = ["unmanaged_file_exists"]
const HASH_TYPES: CheckIssueType[] = ["content_hash_changed", "metadata_hash_changed"]
const PATH_TYPES: CheckIssueType[] = ["current_path_differs_from_canonical_path"]
const LIBRARY_TYPES: CheckIssueType[] = ["library_unregistered", "library_stale", "library_blocked"]

type CheckViewMode = "triage" | "grouped" | "table"

const VIEW_MODE_OPTIONS: SegmentedOption<CheckViewMode>[] = [
  { value: "triage", label: "Triage", icon: ShieldCheck },
  { value: "grouped", label: "Grouped", icon: ListTree },
  { value: "table", label: "Table", icon: Table2 },
]

const GROUP_BY_OPTIONS: { value: CheckGroupBy; label: string }[] = [
  { value: "issue_type", label: "Issue type" },
  { value: "severity", label: "Severity" },
  { value: "path_root", label: "Path root" },
  { value: "artist_album", label: "Artist / album" },
  { value: "suggested_command", label: "Suggested command" },
  { value: "library_id", label: "Library ID" },
]

const SEVERITY_META: Record<
  IssueSeverity,
  { icon: typeof Info; accentBorder: string; accentText: string }
> = {
  error: {
    icon: CircleX,
    accentBorder: "border-l-danger",
    accentText: "text-danger",
  },
  warning: {
    icon: CircleAlert,
    accentBorder: "border-l-warning",
    accentText: "text-warning",
  },
  info: {
    icon: Info,
    accentBorder: "border-l-info",
    accentText: "text-info",
  },
}

/** Quote one shell argument for copyable POSIX-style CLI guidance. */
function quoteShellArg(value: string): string {
  if (value.length === 0) return "''"

  // Single quotes prevent command substitution; embedded single quotes need the standard close-escape-reopen sequence.
  return `'${value.replaceAll("'", `'"'"'`)}'`
}

/** Normalized remediation shown in group headers before an individual path is known. */
function remediationTemplateForIssueType(issueType: CheckIssueType): string {
  switch (issueType) {
    case "db_file_missing":
    case "content_hash_changed":
    case "metadata_hash_changed":
      return "omym2 refresh <file>"
    case "unmanaged_file_exists":
      return "omym2 add <path>"
    case "current_path_differs_from_canonical_path":
    case "duplicate_candidate":
    case "plan_source_changed":
      return "omym2 organize"
    case "pending_file_event_exists":
      return "omym2 history"
    case "library_unregistered":
    case "library_stale":
    case "library_blocked":
      return "omym2 check"
    default:
      return "omym2 check"
  }
}

/** Suggested remediation command per issue type (guidance only, never executed). */
function remediationFor(issue: CheckIssue): string {
  switch (issue.issue_type) {
    case "db_file_missing":
    case "content_hash_changed":
    case "metadata_hash_changed":
      return issue.path
        ? `omym2 refresh ${quoteShellArg(issue.path)}`
        : remediationTemplateForIssueType(issue.issue_type)
    case "unmanaged_file_exists":
      return issue.path
        ? `omym2 add ${quoteShellArg(issue.path)}`
        : remediationTemplateForIssueType(issue.issue_type)
    default:
      return remediationTemplateForIssueType(issue.issue_type)
  }
}

function issueSeverity(issue: CheckIssue): IssueSeverity {
  return issue.severity ?? severityForIssue(issue.issue_type)
}

function issueFacetCounts(facets: Record<string, { value: string; count: number }[]>) {
  return Object.fromEntries(
    facets.issue_type?.map((facet) => [facet.value, facet.count]) ?? [],
  ) as Partial<Record<CheckIssueType, number>>
}

function sumIssueCounts(
  counts: Partial<Record<CheckIssueType, number>>,
  issueTypes: CheckIssueType[],
): number {
  return issueTypes.reduce((total, issueType) => total + (counts[issueType] ?? 0), 0)
}

function totalIssueCount(counts: Partial<Record<CheckIssueType, number>>): number {
  return Object.values(counts).reduce((total, count) => total + (count ?? 0), 0)
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function issueKey(issue: CheckIssue, index: number): string {
  return (
    issue.issue_id ??
    `${issue.issue_type}-${issue.library_id}-${issue.path ?? issue.track_id ?? issue.plan_id ?? "none"}-${index}`
  )
}

function IssueCard({ issue }: { issue: CheckIssue }) {
  const severity = issueSeverity(issue)
  const command = remediationFor(issue)
  return (
    <li
      className={cn(
        "rounded-md border border-hairline border-l-2 bg-surface px-3.5 py-3",
        SEVERITY_META[severity].accentBorder,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">{truncateLabel(issue.issue_type)}</span>
        <StatusBadge status={severity} />
        <Mono className="text-xs text-mute" title={issue.library_id}>
          {truncateMiddle(issue.library_id, 14)}
        </Mono>
      </div>
      {issue.path ? (
        <div className="mt-1.5 flex items-center gap-1">
          <Mono className="min-w-0 truncate text-ink" title={issue.path}>
            {truncateMiddle(issue.path, 64)}
          </Mono>
          <CopyButton value={issue.path} label="Copy path" />
        </div>
      ) : null}
      {issue.detail ? (
        <p className="mt-1 text-xs leading-relaxed text-mute">{issue.detail}</p>
      ) : null}
      <CliCommand command={command} className="mt-2" />
      {issue.track_id || issue.plan_id ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          {issue.track_id ? (
            <Mono className="text-xs text-mute" title={issue.track_id}>
              track: {truncateMiddle(issue.track_id, 14)}
            </Mono>
          ) : null}
          {issue.plan_id ? (
            <Mono className="text-xs text-mute" title={issue.plan_id}>
              plan: {truncateMiddle(issue.plan_id, 14)}
            </Mono>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

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

function isIssueSeverity(value: string): value is IssueSeverity {
  return value === "error" || value === "warning" || value === "info"
}

function groupSeverity(groupBy: CheckGroupBy, group: CheckGroupCount): IssueSeverity | null {
  if (groupBy === "issue_type") {
    return severityForIssue(group.key as CheckIssueType)
  }
  return groupBy === "severity" && isIssueSeverity(group.key) ? group.key : null
}

function groupSuggestion(groupBy: CheckGroupBy, group: CheckGroupCount): string | null {
  if (groupBy === "issue_type") {
    return remediationTemplateForIssueType(group.key as CheckIssueType)
  }
  return groupBy === "suggested_command" ? group.label : null
}

function formatPathRoot(pathRoot: string): string {
  return pathRoot.startsWith("(") || pathRoot.endsWith("/") ? pathRoot : `${pathRoot}/`
}

function CheckGroupLabel({ groupBy, group }: { groupBy: CheckGroupBy; group: CheckGroupCount }) {
  if (groupBy === "severity" && isIssueSeverity(group.key)) {
    return <StatusBadge status={group.key} />
  }
  if (groupBy === "issue_type") {
    return <span className="truncate font-medium text-ink">{truncateLabel(group.label)}</span>
  }
  if (groupBy === "path_root" || groupBy === "library_id" || groupBy === "suggested_command") {
    return (
      <Mono className="truncate text-ink" title={group.label}>
        {group.label}
      </Mono>
    )
  }
  return (
    <span className="truncate font-medium text-ink" title={group.label}>
      {group.label}
    </span>
  )
}

function CheckGroupIssueList({
  groupBy,
  groupKey,
  total,
  query,
  issueType,
}: {
  groupBy: CheckGroupBy
  groupKey: string
  total: number
  query: string
  issueType: CheckIssueType | "all"
}) {
  const loadIssuesPage = useCallback(
    (cursor?: string) =>
      getCheckPage({
        cursor,
        groupBy,
        groupKey,
        query: query.trim() || undefined,
        issueType,
        limit: cursor ? CHECK_GROUP_ISSUE_PAGE_LIMIT : CHECK_EXAMPLE_PAGE_LIMIT,
      }),
    [groupBy, groupKey, issueType, query],
  )
  const issuesPage = usePagedList<CheckIssue>({
    errorMessage: "Group issues failed to load.",
    loadPage: loadIssuesPage,
  })

  return (
    <div className="flex flex-col">
      {issuesPage.errors.length > 0 ? (
        <Notice tone="warning" title="Group issues are incomplete" className="my-2">
          {issuesPage.errors.join(" ")}
        </Notice>
      ) : null}
      {issuesPage.items.length === 0 ? (
        <p className="py-2 text-sm text-mute">
          {issuesPage.loaded ? "No issues in this group." : "Loading examples..."}
        </p>
      ) : (
        <ul className="grid gap-2 py-2 xl:grid-cols-2">
          {issuesPage.items.map((issue, index) => (
            <IssueCard key={issueKey(issue, index)} issue={issue} />
          ))}
        </ul>
      )}
      {issuesPage.items.length > 0 ? (
        <LoadMoreFooter
          className="rounded-md"
          shown={issuesPage.items.length}
          total={issuesPage.page?.total ?? total}
          hasMore={issuesPage.hasMore}
          loading={issuesPage.loadingMore}
          onLoadMore={issuesPage.loadMore}
          noun="issue"
        />
      ) : null}
    </div>
  )
}

function CheckGroupRow({
  groupBy,
  group,
  query,
  issueType,
  expanded,
  onToggle,
}: {
  groupBy: CheckGroupBy
  group: CheckGroupCount
  query: string
  issueType: CheckIssueType | "all"
  expanded: boolean
  onToggle: () => void
}) {
  const contentId = useId()
  const severity = groupSeverity(groupBy, group)
  const suggestion = groupSuggestion(groupBy, group)
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
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <CheckGroupLabel groupBy={groupBy} group={group} />
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-mute">
            {severity && groupBy !== "severity" ? <StatusBadge status={severity} /> : null}
            {group.common_path_root ? (
              <Mono className="text-xs text-mute" title={group.common_path_root}>
                common root: {formatPathRoot(group.common_path_root)}
              </Mono>
            ) : null}
            {suggestion ? (
              <Mono className="text-xs text-mute" title={suggestion}>
                suggested: {suggestion}
              </Mono>
            ) : null}
          </span>
        </span>
        <span className="shrink-0 tabular-nums text-mute">
          {group.count} issue{group.count === 1 ? "" : "s"}
        </span>
        <span className="shrink-0 text-xs font-medium text-mute">
          {expanded ? "Hide examples" : "Show examples"}
        </span>
      </button>
      {expanded ? (
        <div
          id={contentId}
          className="border-t border-hairline bg-surface-canvas/60 py-1 pl-9 pr-3"
        >
          <CheckGroupIssueList
            groupBy={groupBy}
            groupKey={group.key}
            total={group.count}
            query={query}
            issueType={issueType}
          />
        </div>
      ) : null}
    </li>
  )
}

function CheckIssueGroups({
  groupBy,
  checkedAt,
  query,
  issueType,
}: {
  groupBy: CheckGroupBy
  checkedAt: string | null | undefined
  query: string
  issueType: CheckIssueType | "all"
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const loadGroupsPage = useCallback(
    (cursor?: string) =>
      getCheckGroups({
        groupBy,
        cursor,
        limit: CHECK_GROUP_PAGE_LIMIT,
        query: query.trim() || undefined,
        issueType,
      }),
    [groupBy, issueType, query],
  )
  const groupsPage = usePagedList<CheckGroupCount>({
    errorMessage: "Check issue groups failed to load.",
    loadPage: loadGroupsPage,
  })
  const groups = groupsPage.items
  const hasFilters = query.trim() !== "" || issueType !== "all"

  return (
    <div className="flex flex-col gap-4">
      {groupsPage.errors.length > 0 ? (
        <Notice tone="warning" title="Check issue groups are incomplete">
          {groupsPage.errors.join(" ")}
        </Notice>
      ) : null}
      {groups.length === 0 ? (
        <EmptyState
          icon={ListTree}
          title={
            !groupsPage.loaded
              ? "Loading issue groups..."
              : checkedAt === null
                ? "No check has run yet."
                : checkedAt === undefined
                  ? "Check data unavailable."
                  : hasFilters
                    ? "No issue groups match your filters."
                    : "No issue groups to show."
          }
          description={
            !groupsPage.loaded
              ? "Issue concentrations will appear here once they are loaded."
              : checkedAt === null
                ? "Run omym2 check to persist DB and filesystem diagnostics."
                : hasFilters
                  ? "Clear filters or adjust your search to see persisted diagnostics."
                  : "DB and filesystem state appear consistent."
          }
        />
      ) : (
        <div className="overflow-hidden rounded-md border border-hairline">
          <ul className="flex flex-col">
            {groups.map((group) => (
              <CheckGroupRow
                key={group.key}
                groupBy={groupBy}
                group={group}
                query={query}
                issueType={issueType}
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

function CheckIssueTable({
  issueType,
  query,
  checkedAt,
  onCheckedAt,
}: {
  issueType: CheckIssueType | "all"
  query: string
  checkedAt: string | null | undefined
  onCheckedAt: (checkedAt: string | null) => void
}) {
  const loadIssuesPage = useCallback(
    async (cursor?: string) => {
      const response = await getCheckPage({
        cursor,
        query: query.trim() || undefined,
        issueType,
        limit: CHECK_TABLE_PAGE_LIMIT,
      })
      onCheckedAt(response.checked_at)
      return response
    },
    [issueType, onCheckedAt, query],
  )
  const issuesPage = usePagedList<CheckIssue>({
    errorMessage: "Check issues failed to load.",
    loadPage: loadIssuesPage,
  })
  const hasFilters = query.trim() !== "" || issueType !== "all"

  const columns: Column<CheckIssue>[] = [
    {
      key: "issue_type",
      header: "Issue type",
      cell: (issue) => (
        <span className="font-medium text-ink">{truncateLabel(issue.issue_type)}</span>
      ),
      className: "min-w-[12rem]",
    },
    {
      key: "severity",
      header: "Severity",
      cell: (issue) => <StatusBadge status={issueSeverity(issue)} iconOnly />,
      className: "w-20 text-center",
    },
    {
      key: "path",
      header: "Path",
      cell: (issue) =>
        issue.path ? (
          <span className="flex min-w-0 items-center gap-1">
            <Mono className="truncate text-ink" title={issue.path}>
              {truncateMiddle(issue.path, 48)}
            </Mono>
            <CopyButton value={issue.path} label="Copy path" />
          </span>
        ) : (
          <span className="text-mute">—</span>
        ),
      className: "min-w-[20rem]",
    },
    {
      key: "library_id",
      header: "Library",
      cell: (issue) => (
        <Mono className="text-mute" title={issue.library_id}>
          {truncateMiddle(issue.library_id, 16)}
        </Mono>
      ),
      className: "min-w-[10rem]",
    },
    {
      key: "track_id",
      header: "Track",
      cell: (issue) =>
        issue.track_id ? (
          <Mono className="text-mute" title={issue.track_id}>
            {truncateMiddle(issue.track_id, 16)}
          </Mono>
        ) : (
          <span className="text-mute">—</span>
        ),
      className: "min-w-[10rem]",
    },
    {
      key: "plan_id",
      header: "Plan",
      cell: (issue) =>
        issue.plan_id ? (
          <Mono className="text-mute" title={issue.plan_id}>
            {truncateMiddle(issue.plan_id, 16)}
          </Mono>
        ) : (
          <span className="text-mute">—</span>
        ),
      className: "min-w-[10rem]",
    },
    {
      key: "detail",
      header: "Detail",
      cell: (issue) => issue.detail ?? <span className="text-mute">—</span>,
      className: "min-w-[18rem] text-mute",
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      {issuesPage.errors.length > 0 ? (
        <Notice tone="warning" title="Check issues are incomplete">
          {issuesPage.errors.join(" ")}
        </Notice>
      ) : null}
      <DataTable
        columns={columns}
        rows={issuesPage.items}
        getRowKey={issueKey}
        caption="Check issues"
        empty={
          <EmptyState
            icon={ShieldCheck}
            title={
              !issuesPage.loaded
                ? "Loading issues..."
                : checkedAt === null
                  ? "No check has run yet."
                  : checkedAt === undefined
                    ? "Check data unavailable."
                    : hasFilters
                      ? "No issues match your filters."
                      : "No issues found."
            }
            description={
              !issuesPage.loaded
                ? "Current diagnostics will appear here once they are loaded."
                : checkedAt === null
                  ? "Run omym2 check to persist DB and filesystem diagnostics."
                  : hasFilters
                    ? "Clear filters or adjust your search to see persisted diagnostics."
                    : "DB and filesystem state appear consistent."
            }
          />
        }
        loadMore={{
          hasMore: issuesPage.hasMore,
          loading: issuesPage.loadingMore,
          onLoadMore: issuesPage.loadMore,
          total: issuesPage.page?.total ?? issuesPage.items.length,
        }}
      />
    </div>
  )
}

export function CheckScreen() {
  const [viewMode, setViewMode] = useState<CheckViewMode>("triage")
  const [groupBy, setGroupBy] = useState<CheckGroupBy>("path_root")
  const [typeFilter, setTypeFilter] = useState<CheckIssueType | "all">("all")
  const [query, setQuery] = useState("")
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS)
  const [issueTypeCounts, setIssueTypeCounts] = useState<Partial<Record<CheckIssueType, number>>>(
    {},
  )
  const [checkedAt, setCheckedAt] = useState<string | null | undefined>(undefined)
  const [facetTotal, setFacetTotal] = useState<number | null>(null)
  const [facetErrors, setFacetErrors] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    getCheckFacets({ query: debouncedQuery.trim() || undefined })
      .then((response) => {
        if (cancelled) return
        setIssueTypeCounts(issueFacetCounts(response.facets))
        setCheckedAt(response.checked_at)
        setFacetTotal(response.total)
        setFacetErrors(response.errors)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setIssueTypeCounts({})
        setFacetTotal(null)
        setFacetErrors([errorMessage(error, "Check summary failed to load.")])
      })
    return () => {
      cancelled = true
    }
  }, [debouncedQuery])

  const counts = useMemo(() => {
    return {
      total: facetTotal ?? totalIssueCount(issueTypeCounts),
      missing: sumIssueCounts(issueTypeCounts, MISSING_TYPES),
      unmanaged: sumIssueCounts(issueTypeCounts, UNMANAGED_TYPES),
      hash: sumIssueCounts(issueTypeCounts, HASH_TYPES),
      path: sumIssueCounts(issueTypeCounts, PATH_TYPES),
      library: sumIssueCounts(issueTypeCounts, LIBRARY_TYPES),
    }
  }, [facetTotal, issueTypeCounts])

  const checkHasRun = checkedAt !== null && checkedAt !== undefined
  const activeGroupBy: CheckGroupBy = viewMode === "triage" ? "issue_type" : groupBy
  const browseTotal = typeFilter === "all" ? facetTotal : (issueTypeCounts[typeFilter] ?? 0)

  return (
    <>
      <PageHeading
        title="Check"
        description="Read-only DB and filesystem consistency diagnostics. Review issue concentrations before drilling into individual findings."
      />

      <section
        aria-label="Issue summary"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      >
        <MetricCard
          label="Total issues"
          value={counts.total}
          tone={counts.total ? "warning" : checkHasRun ? "success" : "neutral"}
        />
        <MetricCard
          label="Missing files"
          value={counts.missing}
          tone={counts.missing ? "danger" : "neutral"}
        />
        <MetricCard
          label="Unmanaged"
          value={counts.unmanaged}
          tone={counts.unmanaged ? "warning" : "neutral"}
        />
        <MetricCard
          label="Hash changes"
          value={counts.hash}
          tone={counts.hash ? "warning" : "neutral"}
        />
        <MetricCard
          label="Path mismatch"
          value={counts.path}
          tone={counts.path ? "warning" : "neutral"}
        />
        <MetricCard
          label="Library state"
          value={counts.library}
          tone={counts.library ? "warning" : "neutral"}
        />
      </section>

      <Panel
        title={viewMode === "table" ? "Issues" : "Issue groups"}
        icon={viewMode === "table" ? Table2 : ShieldCheck}
        bodyClassName="flex flex-col gap-4"
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <SegmentedControl
              ariaLabel="Check view mode"
              size="sm"
              options={VIEW_MODE_OPTIONS}
              value={viewMode}
              onChange={setViewMode}
            />
            {viewMode === "grouped" ? (
              <div className="w-48">
                <Select
                  aria-label="Group issues by"
                  options={GROUP_BY_OPTIONS}
                  value={groupBy}
                  onChange={(event) => setGroupBy(event.target.value as CheckGroupBy)}
                />
              </div>
            ) : null}
          </div>
        }
      >
        <BrowseFilters
          query={query}
          onQueryChange={setQuery}
          searchHelp="Match paths, details, or Library, Track, and Plan IDs."
          searchPlaceholder="Search Check issues…"
          total={browseTotal}
          facets={[
            {
              key: "issue_type",
              label: "Issue type",
              value: typeFilter,
              options: countedFacetOptions(
                ISSUE_TYPE_OPTIONS,
                Object.entries(issueTypeCounts).map(([value, count]): FacetValue => ({
                  value,
                  count: count ?? 0,
                })),
              ),
              onChange: (value) => setTypeFilter(value as CheckIssueType | "all"),
            },
          ]}
        />

        {facetErrors.length > 0 ? (
          <Notice tone="warning" title="Check summary is incomplete">
            {facetErrors.join(" ")}
          </Notice>
        ) : null}

        {viewMode === "table" ? (
          <CheckIssueTable
            issueType={typeFilter}
            query={debouncedQuery}
            checkedAt={checkedAt}
            onCheckedAt={setCheckedAt}
          />
        ) : (
          <CheckIssueGroups
            key={`${viewMode}-${activeGroupBy}`}
            groupBy={activeGroupBy}
            checkedAt={checkedAt}
            query={debouncedQuery}
            issueType={typeFilter}
          />
        )}
      </Panel>
    </>
  )
}
