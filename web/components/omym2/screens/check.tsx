"use client"

import { ShieldCheck } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { severityForIssue, truncateMiddle } from "../lib"
import type { CheckIssue, CheckIssueType } from "../types"
import {
  DataTable,
  EmptyState,
  MetricCard,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  truncateLabel,
  type Column,
} from "../primitives"
import { Field, Select } from "../forms"
import { CliCommand } from "../widgets"
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

  const libraryOptions = useMemo(
    () =>
      Array.from(new Set(checkIssues.map((issue) => issue.library_id))).map((libraryId) => ({
        value: libraryId,
        label: truncateMiddle(libraryId, 24),
      })),
    [checkIssues],
  )
  const libraryValue = libraryOptions[0]?.value ?? "all"

  const columns: Column<CheckIssue>[] = [
    {
      key: "issue_type",
      header: "Issue type",
      cell: (i) => <span className="font-medium">{truncateLabel(i.issue_type)}</span>,
    },
    {
      key: "severity",
      header: "Severity",
      cell: (i) => <StatusBadge status={i.severity ?? severityForIssue(i.issue_type)} />,
    },
    {
      key: "library_id",
      header: "Library",
      cell: (i) => (
        <Mono className="text-muted-foreground" title={i.library_id}>
          {truncateMiddle(i.library_id, 14)}
        </Mono>
      ),
    },
    {
      key: "path",
      header: "Path",
      cell: (i) => (
        <Mono className="text-foreground" title={i.path ?? undefined}>
          {i.path ? truncateMiddle(i.path, 32) : "—"}
        </Mono>
      ),
      className: "min-w-[14rem]",
    },
    {
      key: "track_id",
      header: "Track",
      cell: (i) =>
        i.track_id ? (
          <Mono className="text-muted-foreground" title={i.track_id}>
            {truncateMiddle(i.track_id, 14)}
          </Mono>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "plan_id",
      header: "Plan",
      cell: (i) =>
        i.plan_id ? (
          <Mono className="text-muted-foreground" title={i.plan_id}>
            {truncateMiddle(i.plan_id, 14)}
          </Mono>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "detail",
      header: "Detail",
      cell: (i) => <span className="text-muted-foreground">{i.detail ?? "—"}</span>,
      className: "max-w-sm",
    },
  ]

  return (
    <>
      <PageHeading
        title="Check"
        description="Read-only DB and filesystem consistency diagnostics. Remediation is performed through the CLI."
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
          title="Issues"
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

          <DataTable
            columns={columns}
            rows={filtered}
            getRowKey={(i, index) =>
              i.issue_id ??
              `${i.issue_type}-${i.library_id}-${i.path ?? i.track_id ?? i.plan_id ?? "none"}-${index}`
            }
            caption="Consistency issues"
            empty={
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
            }
          />
        </Panel>

        <Panel
          title="Remediation hints"
          description="Suggested CLI commands. Not executed from this console."
        >
          <div className="flex flex-col gap-2">
            <CliCommand command="omym2 check" description="Re-run diagnostics." />
            <CliCommand
              command="omym2 refresh <library-file>"
              description="Refresh DB state for a file."
            />
            <CliCommand command="omym2 organize" description="Re-plan canonical placement." />
            <CliCommand command="omym2 history" description="Review related runs and events." />
            {checkIssues.length === 0 && checkLoaded ? (
              <Notice tone="success" title="Consistent" className="mt-1">
                No remediation needed for the selected scan.
              </Notice>
            ) : null}
          </div>
        </Panel>
      </div>
    </>
  )
}
