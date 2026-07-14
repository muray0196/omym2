/**
 * Summary: Renders URL-backed, cursor-paginated Run history.
 * Why: Makes durable execution evidence inspectable without exposing mutations.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue } from "react";
import { Link, useLocation } from "react-router-dom";

import { historyCopy } from "../../features/history/history-copy";
import {
  formatTimestamp,
  runStatusLabel,
} from "../../features/history/history-catalog";
import { RunStatusBadge } from "../../features/history/history-presentation";
import {
  historyFacetsQuery,
  historyInfiniteQuery,
} from "../../features/history/history-query";
import {
  runStatusOptions,
  useHistoryFilters,
} from "../../features/history/history-url-state";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import styles from "../../features/inspection/inspection.module.css";
import { useCursorPage } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";

const numberFormatter = new Intl.NumberFormat("en-US");

export function Component() {
  const location = useLocation();
  const { filters, hasActiveFilters, resetFilters, updateFilters } =
    useHistoryFilters();
  const deferredQuery = useDeferredValue(filters.query);
  const queryFilters = { ...filters, query: deferredQuery };
  const runsQuery = useInfiniteQuery(historyInfiniteQuery(queryFilters));
  const facetsQuery = useQuery(historyFacetsQuery(filters.libraryId));
  const runPage = useCursorPage({
    fetchNextPage: runsQuery.fetchNextPage,
    hasNextPage: runsQuery.hasNextPage,
    isFetchingNextPage: runsQuery.isFetchingNextPage,
    pages: runsQuery.data?.pages,
    resetKey: JSON.stringify(queryFilters),
  });
  const runs = runPage.page?.items ?? [];
  const total = runsQuery.data?.pages[0]?.page.total ?? 0;

  return (
    <article className={styles.page}>
      <PageHeader
        description={historyCopy.list.description}
        eyebrow={historyCopy.list.eyebrow}
        title={historyCopy.list.title}
      />
      <section className={toolbarStyles.toolbar} aria-label="Run filters">
        <label className={toolbarStyles.search}>
          <VisuallyHidden>{historyCopy.list.searchLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            data-list-search
            name="run-search"
            type="search"
            value={filters.query}
            placeholder={historyCopy.list.searchPlaceholder}
            onChange={(event) =>
              updateFilters({ query: event.currentTarget.value })
            }
          />
        </label>
        <label className={toolbarStyles.control}>
          <VisuallyHidden>{historyCopy.list.statusLabel}</VisuallyHidden>
          <select
            name="run-status"
            value={filters.status ?? ""}
            onChange={(event) =>
              updateFilters({
                status:
                  event.currentTarget.value === ""
                    ? undefined
                    : (event.currentTarget.value as typeof filters.status),
              })
            }
          >
            <option value="">{historyCopy.list.allStatuses}</option>
            {runStatusOptions.map((status) => (
              <option key={status} value={status}>
                {runStatusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <label className={toolbarStyles.wideControl}>
          <VisuallyHidden>{historyCopy.list.planLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            name="run-plan-id"
            placeholder={`${historyCopy.list.planLabel}…`}
            value={filters.planId}
            onChange={(event) =>
              updateFilters({ planId: event.currentTarget.value })
            }
          />
        </label>
        <label className={toolbarStyles.wideControl}>
          <VisuallyHidden>{historyCopy.list.libraryLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            name="run-library-id"
            placeholder={`${historyCopy.list.libraryLabel}…`}
            value={filters.libraryId}
            onChange={(event) =>
              updateFilters({ libraryId: event.currentTarget.value })
            }
          />
        </label>
        <div className={toolbarStyles.actions}>
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {historyCopy.list.reset}
            </Button>
          ) : null}
          {runsQuery.data !== undefined ? (
            <p aria-live="polite" className={toolbarStyles.resultCount}>
              {numberFormatter.format(total)} matching Runs
            </p>
          ) : null}
        </div>
        {facetsQuery.data ? (
          <div
            aria-label="Run status counts"
            className={toolbarStyles.secondaryRow}
          >
            <ul className={styles.facetStrip}>
              {facetsQuery.data.facets.status.map((facet) => (
                <li className={styles.facetCompact} key={facet.value}>
                  <RunStatusBadge value={facet.value} />
                  <span className={styles.count}>
                    {numberFormatter.format(facet.count)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
      {runsQuery.isPending ? (
        <section className={styles.state} role="status">
          {historyCopy.list.loading}
        </section>
      ) : null}
      {runsQuery.isError ? (
        <InspectionErrorState
          error={runsQuery.error}
          onRetry={() => void runsQuery.refetch()}
          title={historyCopy.list.error}
        />
      ) : null}
      {runsQuery.isSuccess ? (
        <section className={styles.section}>
          <h2>Recorded Runs</h2>
          {runs.length === 0 ? (
            <p>{historyCopy.list.empty}</p>
          ) : (
            <ul className={styles.list}>
              <li aria-hidden="true" className={styles.historyColumnHeader}>
                <span>Run ID</span>
                <span>Plan ID</span>
                <span>Status</span>
                <span>Started</span>
              </li>
              {runs.map((run) => (
                <li
                  className={`${styles.row} ${styles.historyRow}`}
                  key={run.run_id}
                >
                  <Link
                    className={styles.rowLink}
                    data-list-item
                    to={{
                      pathname: `/history/${run.run_id}`,
                      search: location.search,
                    }}
                  >
                    <span
                      className={`${styles.id} ${styles.historyIdentifier}`}
                      title={run.run_id}
                      translate="no"
                    >
                      {run.run_id}
                    </span>
                    <span
                      className={`${styles.id} ${styles.historyPlan}`}
                      title={run.plan_id}
                      translate="no"
                    >
                      {run.plan_id}
                    </span>
                    <span className={styles.historyStatus}>
                      <RunStatusBadge value={run.status} />
                    </span>
                    <time
                      className={styles.historyStarted}
                      dateTime={run.started_at}
                      title={formatTimestamp(run.started_at)}
                    >
                      {formatTimestamp(run.started_at)}
                    </time>
                    {run.error_summary ? (
                      <p className={styles.historyError}>{run.error_summary}</p>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {runs.length > 0 && runPage.page !== undefined ? (
            <CursorPageControls
              collectionLabel="Runs"
              pageSize={runPage.page.page.limit}
              totalItems={runPage.page.page.total}
              {...runPage}
            />
          ) : null}
        </section>
      ) : null}
    </article>
  );
}
