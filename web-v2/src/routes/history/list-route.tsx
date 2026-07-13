/**
 * Summary: Renders URL-backed, cursor-paginated Run history.
 * Why: Makes durable execution evidence inspectable without exposing mutations.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

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
import { Button } from "../../ui/primitives/button";
import { RouteHeading } from "../../ui/primitives/route-heading";

export function Component() {
  const { filters, hasActiveFilters, resetFilters, updateFilters } =
    useHistoryFilters();
  const runsQuery = useInfiniteQuery(historyInfiniteQuery(filters));
  const facetsQuery = useQuery(historyFacetsQuery(filters.libraryId));
  const runs = runsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const total = runsQuery.data?.pages[0]?.page.total ?? 0;

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{historyCopy.list.eyebrow}</p>
        <RouteHeading>{historyCopy.list.title}</RouteHeading>
        <p className={styles.description}>{historyCopy.list.description}</p>
      </header>
      <section className={styles.filters} aria-label="Run filters">
        <div className={styles.filterGrid}>
          <label className={styles.field}>
            {historyCopy.list.searchLabel}
            <input
              type="search"
              value={filters.query}
              placeholder={historyCopy.list.searchPlaceholder}
              onChange={(event) =>
                updateFilters({ query: event.currentTarget.value })
              }
            />
          </label>
          <label className={styles.field}>
            {historyCopy.list.statusLabel}
            <select
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
          <label className={styles.field}>
            {historyCopy.list.planLabel}
            <input
              value={filters.planId}
              onChange={(event) =>
                updateFilters({ planId: event.currentTarget.value })
              }
            />
          </label>
          <label className={styles.field}>
            {historyCopy.list.libraryLabel}
            <input
              value={filters.libraryId}
              onChange={(event) =>
                updateFilters({ libraryId: event.currentTarget.value })
              }
            />
          </label>
        </div>
        <div className={styles.actions}>
          <p className={styles.subtle}>{total} matching Runs</p>
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {historyCopy.list.reset}
            </Button>
          ) : null}
        </div>
      </section>
      {facetsQuery.data ? (
        <section className={styles.section}>
          <h2>Run status counts</h2>
          <ul className={styles.facetList}>
            {facetsQuery.data.facets.status.map((facet) => (
              <li className={styles.facet} key={facet.value}>
                <RunStatusBadge value={facet.value} />
                <span className={styles.count}>{facet.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
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
              {runs.map((run) => (
                <li className={styles.row} key={run.run_id}>
                  <Link
                    className={styles.rowLink}
                    to={`/history/${run.run_id}`}
                  >
                    <div className={styles.rowHeader}>
                      <span className={styles.id}>{run.run_id}</span>
                      <RunStatusBadge value={run.status} />
                    </div>
                    <div className={styles.metadata}>
                      <span>
                        Plan <span className={styles.id}>{run.plan_id}</span>
                      </span>
                      <span>{formatTimestamp(run.started_at)}</span>
                    </div>
                    {run.error_summary ? <p>{run.error_summary}</p> : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {runsQuery.hasNextPage ? (
            <Button
              disabled={runsQuery.isFetchingNextPage}
              onClick={() => void runsQuery.fetchNextPage()}
            >
              {runsQuery.isFetchingNextPage
                ? historyCopy.list.loadingMore
                : historyCopy.list.loadMore}
            </Button>
          ) : null}
        </section>
      ) : null}
    </article>
  );
}
