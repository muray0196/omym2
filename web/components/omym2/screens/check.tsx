/*
Summary: Renders persisted consistency-check findings.
Why: Lets users triage stored issues without recomputing checks on page load.
*/

"use client"

import { ChevronDown, CircleAlert, CircleX, Info, ShieldCheck } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { getCheckFacets, getCheckPage } from "../api-client"
import { cn, severityForIssue, truncateMiddle } from "../lib"
import type { CheckIssue, CheckIssueType, IssueSeverity } from "../types"
import { usePagedList } from "../use-paged-list"
import {
  Button,
  CopyButton,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  truncateLabel,
} from "../primitives"
import { CliCommand } from "../widgets"
import { Field, Select } from "../forms"

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

const CHECK_PAGE_LIMIT = 100

const MISSING_TYPES: CheckIssueType[] = ["db_file_missing"]
const UNMANAGED_TYPES: CheckIssueType[] = ["unmanaged_file_exists"]
const HASH_TYPES: CheckIssueType[] = ["content_hash_changed", "metadata_hash_changed"]
const PATH_TYPES: CheckIssueType[] = ["current_path_differs_from_canonical_path"]
const LIBRARY_TYPES: CheckIssueType[] = ["library_unregistered", "library_stale", "library_blocked"]

/** Quote one shell argument for copyable POSIX-style CLI guidance. */
function quoteShellArg(value: string): string {
  if (value.length === 0) return "''"

  // Single quotes prevent command substitution; embedded single quotes need the standard close-escape-reopen sequence.
  return `'${value.replaceAll("'", `'"'"'`)}'`
}

/** Suggested remediation command per issue type (guidance only, never executed). */
function remediationFor(issue: CheckIssue): string {
  switch (issue.issue_type) {
    case "db_file_missing":
    case "content_hash_changed":
    case "metadata_hash_changed":
      return issue.path
        ? `omym2 refresh ${quoteShellArg(issue.path)}`
        : "omym2 refresh <library-file>"
    case "unmanaged_file_exists":
      return issue.path ? `omym2 add ${quoteShellArg(issue.path)}` : "omym2 add <path>"
    case "current_path_differs_from_canonical_path":
    case "duplicate_candidate":
      return "omym2 organize"
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

const SEVERITY_ORDER: IssueSeverity[] = ["error", "warning", "info"]

const SEVERITY_META: Record<
  IssueSeverity,
  { label: string; icon: typeof Info; accentBorder: string; accentText: string }
> = {
  error: {
    label: "Errors — act first",
    icon: CircleX,
    accentBorder: "border-l-danger",
    accentText: "text-danger",
  },
  warning: {
    label: "Warnings — review soon",
    icon: CircleAlert,
    accentBorder: "border-l-warning",
    accentText: "text-warning",
  },
  info: {
    label: "Info — awareness only",
    icon: Info,
    accentBorder: "border-l-info",
    accentText: "text-info",
  },
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

export function CheckScreen() {
  const [typeFilter, setTypeFilter] = useState<CheckIssueType | "all">("all")
  const [issueTypeCounts, setIssueTypeCounts] = useState<Partial<Record<CheckIssueType, number>>>(
    {},
  )
  const [facetTotal, setFacetTotal] = useState<number | null>(null)
  const [facetErrors, setFacetErrors] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    getCheckFacets()
      .then((response) => {
        if (cancelled) return
        setIssueTypeCounts(issueFacetCounts(response.facets))
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
  }, [])

  const loadIssuesPage = useCallback(
    (cursor?: string) =>
      getCheckPage({
        cursor,
        issueType: typeFilter,
        limit: CHECK_PAGE_LIMIT,
      }),
    [typeFilter],
  )
  const issuesPage = usePagedList({
    errorMessage: "Check issues failed to load.",
    loadPage: loadIssuesPage,
  })
  const checkIssues = issuesPage.items
  const checkErrors = [...issuesPage.errors, ...facetErrors]
  const checkLoaded = issuesPage.loaded

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

  const grouped = useMemo(() => {
    const buckets: Record<IssueSeverity, CheckIssue[]> = { error: [], warning: [], info: [] }
    for (const issue of checkIssues) buckets[issueSeverity(issue)].push(issue)
    return buckets
  }, [checkIssues])

  return (
    <>
      <PageHeading
        title="Check"
        description="Read-only DB and filesystem consistency diagnostics. Issues are triaged by severity; each carries a suggested CLI remediation."
      />

      <section
        aria-label="Issue summary"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      >
        <MetricCard
          label="Total issues"
          value={counts.total}
          tone={counts.total ? "warning" : "success"}
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

      <Panel title="Triage" icon={ShieldCheck} bodyClassName="flex flex-col gap-4">
        <Field label="Issue type" className="sm:max-w-xs">
          {(id) => (
            <Select
              id={id}
              options={ISSUE_TYPE_OPTIONS}
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as CheckIssueType | "all")}
            />
          )}
        </Field>

        {checkErrors.length > 0 ? (
          <Notice tone="warning" title="Check data is incomplete">
            {checkErrors.join(" ")}
          </Notice>
        ) : null}

        {checkIssues.length === 0 ? (
          typeFilter === "all" && counts.total === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title={checkLoaded ? "No issues found." : "Loading issues..."}
              description={
                checkLoaded
                  ? "DB and filesystem state appear consistent."
                  : "Current diagnostics will appear here once they are loaded."
              }
            />
          ) : (
            <EmptyState icon={ShieldCheck} title="No issues match this filter." />
          )
        ) : (
          <div className="flex flex-col gap-5">
            {SEVERITY_ORDER.map((severity) => {
              const issues = grouped[severity]
              if (issues.length === 0) return null
              const meta = SEVERITY_META[severity]
              const Icon = meta.icon
              return (
                <section key={severity} aria-label={meta.label}>
                  <div className="mb-2 flex items-center gap-2">
                    <Icon className={cn("size-4", meta.accentText)} aria-hidden="true" />
                    <h3 className="text-sm font-medium tracking-[0.2px] text-ink">{meta.label}</h3>
                    <span
                      className={cn(
                        "rounded-full bg-surface-elevated px-2 py-0.5 text-xs font-medium tabular-nums",
                        meta.accentText,
                      )}
                    >
                      {issues.length}
                    </span>
                  </div>
                  <ul className="grid gap-2 xl:grid-cols-2">
                    {issues.map((issue, index) => (
                      <IssueCard
                        key={
                          issue.issue_id ??
                          `${issue.issue_type}-${issue.library_id}-${issue.path ?? issue.track_id ?? issue.plan_id ?? "none"}-${index}`
                        }
                        issue={issue}
                      />
                    ))}
                  </ul>
                </section>
              )
            })}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
              <span className="text-xs tabular-nums text-mute">
                {typeFilter === "all"
                  ? `${Math.min(issuesPage.items.length, counts.total)} of ${counts.total} issue${
                      counts.total === 1 ? "" : "s"
                    } loaded`
                  : `${issuesPage.items.length} issue${
                      issuesPage.items.length === 1 ? "" : "s"
                    } loaded`}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!issuesPage.hasMore || issuesPage.loadingMore}
                onClick={issuesPage.loadMore}
              >
                <ChevronDown className="size-4" aria-hidden="true" />
                {issuesPage.loadingMore
                  ? "Loading..."
                  : issuesPage.hasMore
                    ? "Load more"
                    : "All issues loaded"}
              </Button>
            </div>
          </div>
        )}
      </Panel>
    </>
  )
}
