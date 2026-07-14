/**
 * Summary: Renders persisted Check findings with URL-backed grouping and filters.
 * Why: Makes Health evidence inspectable without triggering filesystem work.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue } from "react";

import {
  groupingLabel,
  healthGroupValueLabel,
  issueTypeLabel,
} from "../../features/health/health-catalog";
import { CheckRunControl } from "../../features/health/check-run-control";
import { healthCopy } from "../../features/health/health-copy";
import { IssueTypeValue } from "../../features/health/health-presentation";
import {
  checkIssueFacetsQuery,
  checkIssueGroupsInfiniteQuery,
  checkIssuesInfiniteQuery,
} from "../../features/health/health-query";
import {
  groupingOptions,
  issueTypeOptions,
  useHealthFilters,
} from "../../features/health/health-url-state";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import styles from "../../features/inspection/inspection.module.css";
import { useCursorPage } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";

const numberFormatter = new Intl.NumberFormat("en-US");
const timestampFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function Component() {
  const { clearGroup, filters, hasActiveFilters, resetFilters, updateFilters } =
    useHealthFilters();
  const deferredQuery = useDeferredValue(filters.query);
  const queryFilters = { ...filters, query: deferredQuery };
  const issuesQuery = useInfiniteQuery(checkIssuesInfiniteQuery(queryFilters));
  const facetsQuery = useQuery(checkIssueFacetsQuery(queryFilters));
  const groupsQuery = useInfiniteQuery(
    checkIssueGroupsInfiniteQuery(queryFilters),
  );
  const resetKey = JSON.stringify(queryFilters);
  const issuePage = useCursorPage({
    fetchNextPage: issuesQuery.fetchNextPage,
    hasNextPage: issuesQuery.hasNextPage,
    isFetchingNextPage: issuesQuery.isFetchingNextPage,
    pages: issuesQuery.data?.pages,
    resetKey,
  });
  const groupPage = useCursorPage({
    fetchNextPage: groupsQuery.fetchNextPage,
    hasNextPage: groupsQuery.hasNextPage,
    isFetchingNextPage: groupsQuery.isFetchingNextPage,
    pages: groupsQuery.data?.pages,
    resetKey,
  });
  const issues = issuePage.page?.items ?? [];
  const groups = groupPage.page?.items ?? [];
  const checkedAt =
    issuesQuery.data?.pages[0]?.checked_at ??
    facetsQuery.data?.checked_at ??
    null;
  const total = issuesQuery.data?.pages[0]?.page.total ?? 0;

  return (
    <article className={styles.page}>
      <PageHeader
        description={healthCopy.description}
        eyebrow={healthCopy.eyebrow}
        meta={
          <p>
            {checkedAt
              ? `${healthCopy.freshness} ${formatTimestamp(checkedAt)}`
              : healthCopy.neverChecked}
          </p>
        }
        title={healthCopy.title}
      />
      <CheckRunControl />
      <section className={toolbarStyles.toolbar} aria-label="Health filters">
        <label className={toolbarStyles.search}>
          <VisuallyHidden>{healthCopy.searchLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            data-list-search
            name="health-search"
            type="search"
            placeholder={healthCopy.searchPlaceholder}
            value={filters.query}
            onChange={(event) =>
              updateFilters({ query: event.currentTarget.value })
            }
          />
        </label>
        <label className={toolbarStyles.control}>
          <VisuallyHidden>{healthCopy.issueTypeLabel}</VisuallyHidden>
          <select
            name="health-issue-type"
            value={filters.issueType ?? ""}
            onChange={(event) =>
              updateFilters({
                issueType:
                  event.currentTarget.value === ""
                    ? undefined
                    : (event.currentTarget.value as typeof filters.issueType),
                groupKey: undefined,
              })
            }
          >
            <option value="">{healthCopy.allIssueTypes}</option>
            {issueTypeOptions.map((type) => (
              <option key={type} value={type}>
                {issueTypeLabel(type)}
              </option>
            ))}
          </select>
        </label>
        <label className={toolbarStyles.wideControl}>
          <VisuallyHidden>{healthCopy.groupingLabel}</VisuallyHidden>
          <select
            name="health-grouping"
            value={filters.groupBy}
            onChange={(event) =>
              updateFilters({
                groupBy: event.currentTarget.value as typeof filters.groupBy,
                groupKey: undefined,
              })
            }
          >
            {groupingOptions.map((grouping) => (
              <option key={grouping} value={grouping}>
                {groupingLabel(grouping)}
              </option>
            ))}
          </select>
        </label>
        <label className={toolbarStyles.wideControl}>
          <VisuallyHidden>{healthCopy.libraryLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            name="health-library-id"
            placeholder={`${healthCopy.libraryLabel}…`}
            value={filters.libraryId}
            onChange={(event) =>
              updateFilters({
                libraryId: event.currentTarget.value,
                groupKey: undefined,
              })
            }
          />
        </label>
        <div className={toolbarStyles.actions}>
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {healthCopy.reset}
            </Button>
          ) : null}
          {issuesQuery.data !== undefined ? (
            <p aria-live="polite" className={toolbarStyles.resultCount}>
              {numberFormatter.format(total)} findings
            </p>
          ) : null}
        </div>
        {filters.groupKey || facetsQuery.data ? (
          <div className={toolbarStyles.secondaryRow}>
            {filters.groupKey ? (
              <p className={toolbarStyles.selected}>
                {healthCopy.selectedGroup}:{" "}
                {healthGroupValueLabel(
                  filters.groupBy,
                  filters.groupKey,
                  filters.groupKey,
                )}
              </p>
            ) : null}
            {filters.groupKey ? (
              <Button onClick={clearGroup} variant="quiet">
                {healthCopy.clearGroup}
              </Button>
            ) : null}
            {facetsQuery.data ? (
              <ul aria-label={healthCopy.facets} className={styles.facetStrip}>
                {facetsQuery.data.facets.issue_type.map((facet) => (
                  <li className={styles.facetCompact} key={facet.value}>
                    <IssueTypeValue value={facet.value} />
                    <span className={styles.count}>
                      {numberFormatter.format(facet.count)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>
      <section className={styles.section}>
        <h2>{healthCopy.groups}</h2>
        {groupsQuery.isPending ? (
          <p role="status">Loading finding groups…</p>
        ) : null}
        {groupsQuery.isError ? (
          <InspectionErrorState
            error={groupsQuery.error}
            onRetry={() => void groupsQuery.refetch()}
            title="Finding groups could not be loaded"
          />
        ) : null}
        {groups.length > 0 ? (
          <ul className={styles.groupList}>
            {groups.map((group) => (
              <li className={styles.group} key={group.key}>
                <button
                  className={styles.groupButton}
                  type="button"
                  onClick={() => updateFilters({ groupKey: group.key })}
                >
                  <strong>
                    {(groupPage.page?.group_by ?? filters.groupBy) ===
                    "issue_type" ? (
                      <IssueTypeValue value={group.key} />
                    ) : (
                      healthGroupValueLabel(
                        groupPage.page?.group_by ?? filters.groupBy,
                        group.key,
                        group.label,
                      )
                    )}
                  </strong>
                  {group.common_path_root ? (
                    <span className={styles.path}>
                      {group.common_path_root}
                    </span>
                  ) : null}
                </button>
                <span className={styles.count}>
                  {numberFormatter.format(group.count)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {groupsQuery.isSuccess &&
        groups.length > 0 &&
        groupPage.page !== undefined ? (
          <CursorPageControls
            collectionLabel="Health groups"
            pageSize={groupPage.page.page.limit}
            totalItems={groupPage.page.page.total}
            {...groupPage}
          />
        ) : null}
      </section>
      <section className={styles.section}>
        <h2>{healthCopy.findings}</h2>
        {issuesQuery.isPending ? (
          <p role="status">{healthCopy.loading}</p>
        ) : null}
        {issuesQuery.isError ? (
          <InspectionErrorState
            error={issuesQuery.error}
            onRetry={() => void issuesQuery.refetch()}
            title={healthCopy.error}
          />
        ) : null}
        {issuesQuery.isSuccess && issues.length === 0 ? (
          <p>{healthCopy.empty}</p>
        ) : null}
        {issues.length > 0 ? (
          <ul className={styles.list}>
            <li aria-hidden="true" className={styles.healthColumnHeader}>
              <span>Issue</span>
              <span>Path</span>
              <span>Evidence</span>
              <span>Library</span>
            </li>
            {issues.map((issue, index) => (
              <li
                className={`${styles.row} ${styles.healthRow}`}
                key={`${issue.library_id}:${issue.issue_type}:${issue.path ?? index}`}
              >
                <strong className={styles.healthIssue}>
                  <IssueTypeValue value={issue.issue_type} />
                </strong>
                <span
                  className={`${styles.path} ${styles.healthPath}`}
                  title={issue.path ?? undefined}
                  translate="no"
                >
                  {issue.path ?? "—"}
                </span>
                <div className={styles.healthReferences}>
                  {issue.track_id ? (
                    <span>
                      Track{" "}
                      <span className={styles.id} translate="no">
                        {issue.track_id}
                      </span>
                    </span>
                  ) : null}
                  {issue.plan_id ? (
                    <span>
                      Plan{" "}
                      <span className={styles.id} translate="no">
                        {issue.plan_id}
                      </span>
                    </span>
                  ) : null}
                  {issue.track_id || issue.plan_id ? null : <span>—</span>}
                </div>
                <span
                  className={`${styles.id} ${styles.healthLibrary}`}
                  title={issue.library_id}
                  translate="no"
                >
                  {issue.library_id}
                </span>
                {issue.detail ? (
                  <p className={styles.healthDetail}>{issue.detail}</p>
                ) : null}
                {issue.issue_type === "pending_file_event_exists" ? (
                  <div className={`${styles.warning} ${styles.healthWarning}`}>
                    <strong>Manual review required</strong>
                    <p>{healthCopy.pending}</p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {issuesQuery.isSuccess &&
        issues.length > 0 &&
        issuePage.page !== undefined ? (
          <CursorPageControls
            collectionLabel="Findings"
            pageSize={issuePage.page.page.limit}
            totalItems={issuePage.page.page.total}
            {...issuePage}
          />
        ) : null}
      </section>
    </article>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : timestampFormatter.format(date);
}
