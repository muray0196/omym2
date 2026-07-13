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
import { RouteHeading } from "../../ui/primitives/route-heading";

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

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{healthCopy.eyebrow}</p>
        <RouteHeading>{healthCopy.title}</RouteHeading>
        <p className={styles.description}>{healthCopy.description}</p>
        <p className={styles.subtle}>
          {checkedAt
            ? `${healthCopy.freshness} ${formatTimestamp(checkedAt)}`
            : healthCopy.neverChecked}
        </p>
      </header>
      <CheckRunControl />
      <section className={styles.filters} aria-label="Health filters">
        <div className={styles.filterGrid}>
          <label className={styles.field}>
            {healthCopy.searchLabel}
            <input
              data-list-search
              type="search"
              placeholder={healthCopy.searchPlaceholder}
              value={filters.query}
              onChange={(event) =>
                updateFilters({ query: event.currentTarget.value })
              }
            />
          </label>
          <label className={styles.field}>
            {healthCopy.issueTypeLabel}
            <select
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
          <label className={styles.field}>
            {healthCopy.groupingLabel}
            <select
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
          <label className={styles.field}>
            {healthCopy.libraryLabel}
            <input
              value={filters.libraryId}
              onChange={(event) =>
                updateFilters({
                  libraryId: event.currentTarget.value,
                  groupKey: undefined,
                })
              }
            />
          </label>
        </div>
        <div className={styles.actions}>
          {filters.groupKey ? (
            <p className={styles.selected}>
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
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {healthCopy.reset}
            </Button>
          ) : null}
        </div>
      </section>
      {facetsQuery.data ? (
        <section className={styles.section}>
          <h2>{healthCopy.facets}</h2>
          <ul className={styles.facetList}>
            {facetsQuery.data.facets.issue_type.map((facet) => (
              <li className={styles.facet} key={facet.value}>
                <IssueTypeValue value={facet.value} />
                <span className={styles.count}>{facet.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
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
                <span className={styles.count}>{group.count}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {groupsQuery.isSuccess && groupPage.page !== undefined ? (
          <CursorPageControls collectionLabel="Health groups" {...groupPage} />
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
            {issues.map((issue, index) => (
              <li
                className={styles.row}
                key={`${issue.library_id}:${issue.issue_type}:${issue.path ?? index}`}
              >
                <div className={styles.rowHeader}>
                  <strong>
                    <IssueTypeValue value={issue.issue_type} />
                  </strong>
                  <span className={styles.id}>{issue.library_id}</span>
                </div>
                {issue.path ? (
                  <p className={styles.path}>{issue.path}</p>
                ) : null}
                {issue.detail ? <p>{issue.detail}</p> : null}
                <div className={styles.metadata}>
                  {issue.track_id ? (
                    <span>
                      Track <span className={styles.id}>{issue.track_id}</span>
                    </span>
                  ) : null}
                  {issue.plan_id ? (
                    <span>
                      Plan <span className={styles.id}>{issue.plan_id}</span>
                    </span>
                  ) : null}
                </div>
                {issue.issue_type === "pending_file_event_exists" ? (
                  <div className={styles.warning}>
                    <strong>Manual review required</strong>
                    <p>{healthCopy.pending}</p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {issuesQuery.isSuccess && issuePage.page !== undefined ? (
          <CursorPageControls collectionLabel="Findings" {...issuePage} />
        ) : null}
      </section>
    </article>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
