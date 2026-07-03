"use client"

import { CircleAlert, CircleX, Info, ShieldCheck } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { cn, severityForIssue, truncateMiddle } from "../lib"
import type { CheckIssue, CheckIssueType, IssueSeverity } from "../types"
import {
  CopyButton,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  truncateLabel,
} from "../primitives"
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

const MISSING_TYPES: CheckIssueType[] = ["db_file_missing"]
const UNMANAGED_TYPES: CheckIssueType[] = ["unmanaged_file_exists"]
const HASH_TYPES: CheckIssueType[] = ["content_hash_changed", "metadata_hash_changed"]
const PATH_TYPES: CheckIssueType[] = ["current_path_differs_from_canonical_path"]
const LIBRARY_TYPES: CheckIssueType[] = ["library_unregistered", "library_stale", "library_blocked"]

/** Suggested remediation command per issue type (guidance only, never executed). */
function remediationFor(issue: CheckIssue): string {
  switch (issue.issue_type) {
    case "db_file_missing":
    case "content_hash_changed":
    case "metadata_hash_changed":
      return issue.path ? `omym2 refresh "${issue.path}"` : "omym2 refresh <library-file>"
    case "unmanaged_file_exists":
      return issue.path ? `omym2 add "${issue.path}"` : "omym2 add <path>"
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

function IssueCard({ issue }: { issue: CheckIssue }) {
  const severity = issueSeverity(issue)
  const command = remediationFor(issue)
  return (
    <li
      className={cn(
        "rounded-md border border-border border-l-2 bg-card px-3 py-2.5",
        SEVERITY_META[severity].accentBorder,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{truncateLabel(issue.issue_type)}</span>
        <StatusBadge status={severity} />
        <Mono className="text-xs text-muted-foreground" title={issue.library_id}>
          {truncateMiddle(issue.library_id, 14)}
        </Mono>
      </div>
      {issue.path ? (
        <div className="mt-1.5 flex items-center gap-1">
          <Mono className="min-w-0 truncate text-[0.8125rem] text-foreground" title={issue.path}>
            {truncateMiddle(issue.path, 64)}
          </Mono>
          <CopyButton value={issue.path} label="Copy path" />
        </div>
      ) : null}
      {issue.detail ? <p className="mt-1 text-xs text-muted-foreground">{issue.detail}</p> : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex min-w-0 items-center gap-1.5 rounded border border-border bg-muted/50 px-2 py-1">
          <span className="select-none font-mono text-xs text-muted-foreground">$</span>
          <Mono className="min-w-0 truncate text-xs text-foreground" title={command}>
            {command}
          </Mono>
          <CopyButton value={command} label="Copy remediation command" />
        </span>
        {issue.track_id ? (
          <Mono className="text-xs text-muted-foreground" title={issue.track_id}>
            track: {truncateMiddle(issue.track_id, 14)}
          </Mono>
        ) : null}
        {issue.plan_id ? (
          <Mono className="text-xs text-muted-foreground" title={issue.plan_id}>
            plan: {truncateMiddle(issue.plan_id, 14)}
          </Mono>
        ) : null}
      </div>
    </li>
  )
}

export function CheckScreen() {
  const { checkErrors, checkIssues, checkLoaded } = useApp()
  const [typeFilter, setTypeFilter] = useState("all")

  const counts = useMemo(() => {
    const within = (types: CheckIssueType[]) =>
      checkIssues.filter((i) => types.includes(i.issue_type)).length
    return {
      total: checkIssues.length,
      missing: within(MISSING_TYPES),
      unmanaged: within(UNMANAGED_TYPES),
      hash: within(HASH_TYPES),
      path: within(PATH_TYPES),
      library: within(LIBRARY_TYPES),
    }
  }, [checkIssues])

  const filtered = useMemo(
    () => checkIssues.filter((i) => (typeFilter === "all" ? true : i.issue_type === typeFilter)),
    [checkIssues, typeFilter],
  )

  const grouped = useMemo(() => {
    const buckets: Record<IssueSeverity, CheckIssue[]> = { error: [], warning: [], info: [] }
    for (const issue of filtered) buckets[issueSeverity(issue)].push(issue)
    return buckets
  }, [filtered])

  const libraryOptions = useMemo(
    () =>
      Array.from(new Set(checkIssues.map((issue) => issue.library_id))).map((libraryId) => ({
        value: libraryId,
        label: truncateMiddle(libraryId, 24),
      })),
    [checkIssues],
  )
  const libraryValue = libraryOptions[0]?.value ?? "all"

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

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title="Triage"
          icon={ShieldCheck}
          className="lg:col-span-2"
          bodyClassName="flex flex-col gap-4"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Issue type">
              {(id) => (
                <Select
                  id={id}
                  options={ISSUE_TYPE_OPTIONS}
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                />
              )}
            </Field>
            <Field label="Library">
              {(id) => (
                <Select
                  id={id}
                  options={
                    libraryOptions.length > 0
                      ? libraryOptions
                      : [{ value: "all", label: "All libraries" }]
                  }
                  value={libraryValue}
                  disabled
                />
              )}
            </Field>
          </div>

          {checkErrors.length > 0 ? (
            <Notice tone="warning" title="Check data is incomplete">
              {checkErrors.join(" ")}
            </Notice>
          ) : null}

          {filtered.length === 0 ? (
            checkIssues.length === 0 ? (
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
                      <h3 className="text-sm font-semibold">{meta.label}</h3>
                      <span
                        className={cn(
                          "rounded-full bg-muted px-2 py-0.5 text-xs font-medium tabular-nums",
                          meta.accentText,
                        )}
                      >
                        {issues.length}
                      </span>
                    </div>
                    <ul className="flex flex-col gap-2">
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
            </div>
          )}
        </Panel>


      </div>
    </>
  )
}
