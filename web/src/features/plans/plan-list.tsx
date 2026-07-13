/**
 * Summary: Renders URL-synchronized, cursor-paginated read-only Plan browsing.
 * Why: Lets operators inspect recorded Plans without exposing planning or execution controls.
 */
import { useInfiniteQuery } from "@tanstack/react-query";
import { useDeferredValue } from "react";
import { Link, useLocation } from "react-router-dom";

import { useCursorPage } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { planCopy } from "./plan-copy";
import { PlanErrorState } from "./plan-error-state";
import { PlanStatusBadge, PlanTypeValue } from "./plan-presentation";
import { plansInfiniteQuery, type PlanSummary } from "./plan-query";
import {
  planStatusOptions,
  planTypeOptions,
  usePlanListFilters,
} from "./plan-url-state";
import styles from "./plan-inspection.module.css";

const timestampFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function PlanList() {
  const location = useLocation();
  const { filters, hasActiveFilters, resetFilters, updateFilters } =
    usePlanListFilters();
  const deferredQuery = useDeferredValue(filters.query);
  const queryFilters = { ...filters, query: deferredQuery };
  const query = useInfiniteQuery(plansInfiniteQuery(queryFilters));
  const cursorPage = useCursorPage({
    fetchNextPage: query.fetchNextPage,
    hasNextPage: query.hasNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
    pages: query.data?.pages,
    resetKey: JSON.stringify(queryFilters),
  });
  const plans = cursorPage.page?.items ?? [];
  const total = query.data?.pages[0]?.page.total ?? 0;

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{planCopy.list.eyebrow}</p>
        <RouteHeading>{planCopy.list.title}</RouteHeading>
        <p className={styles.description}>{planCopy.list.description}</p>
      </header>

      <form
        className={styles.filterPanel}
        onSubmit={(event) => event.preventDefault()}
      >
        <div className={styles.filterGrid}>
          <div className={styles.field}>
            <label htmlFor="plan-search">{planCopy.list.searchLabel}</label>
            <input
              data-list-search
              id="plan-search"
              onChange={(event) => updateFilters({ query: event.target.value })}
              placeholder={planCopy.list.searchPlaceholder}
              type="search"
              value={filters.query}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="plan-status">{planCopy.list.statusLabel}</label>
            <select
              id="plan-status"
              onChange={(event) =>
                updateFilters({
                  status: planStatusOptions.find(
                    (option) => option.value === event.target.value,
                  )?.value,
                })
              }
              value={filters.status ?? ""}
            >
              <option value="">{planCopy.list.allStatuses}</option>
              {planStatusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="plan-type">{planCopy.list.typeLabel}</label>
            <select
              id="plan-type"
              onChange={(event) =>
                updateFilters({
                  type: planTypeOptions.find(
                    (option) => option.value === event.target.value,
                  )?.value,
                })
              }
              value={filters.type ?? ""}
            >
              <option value="">{planCopy.list.allTypes}</option>
              {planTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <label className={styles.checkboxLabel}>
          <input
            checked={filters.blocked}
            onChange={(event) =>
              updateFilters({ blocked: event.target.checked })
            }
            type="checkbox"
          />
          {planCopy.list.blockedLabel}
        </label>
        <div className={styles.filterActions}>
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {planCopy.list.resetFilters}
            </Button>
          ) : null}
          {query.data !== undefined ? (
            <p aria-live="polite" className={styles.resultCount}>
              {total} {planCopy.list.resultCount}
            </p>
          ) : null}
        </div>
      </form>

      {query.isPending ? <LoadingState label={planCopy.list.loading} /> : null}
      {query.isError ? (
        <PlanErrorState
          error={query.error}
          onRetry={() => void query.refetch()}
          retryLabel={planCopy.list.retry}
          title={planCopy.list.loadError}
        />
      ) : null}
      {query.isSuccess && plans.length === 0 ? (
        <EmptyState hasActiveFilters={hasActiveFilters} />
      ) : null}
      {query.isSuccess && plans.length > 0 ? (
        <ul aria-label={planCopy.list.title} className={styles.planList}>
          {plans.map((plan) => (
            <PlanRow key={plan.plan_id} plan={plan} search={location.search} />
          ))}
        </ul>
      ) : null}
      {query.isSuccess && cursorPage.page !== undefined ? (
        <CursorPageControls collectionLabel="Plans" {...cursorPage} />
      ) : null}
    </article>
  );
}

function PlanRow({ plan, search }: { plan: PlanSummary; search: string }) {
  const blockedCount = sumActionTypeCounts(plan.summary.counts.blocked);

  return (
    <li className={styles.planRow}>
      <Link
        className={styles.planLink}
        data-list-item
        to={{ pathname: `/plans/${plan.plan_id}`, search }}
      >
        <div className={styles.rowHeader}>
          <code className={styles.id}>{plan.plan_id}</code>
          <PlanStatusBadge value={plan.status} />
        </div>
        <div className={styles.rowMetadata}>
          <PlanTypeValue value={plan.plan_type} />
          <span>
            {plan.summary.total} {planCopy.detail.actionCount}
          </span>
          <span>
            {blockedCount} {planCopy.labels.blocked}
          </span>
          <time dateTime={plan.created_at}>
            {formatTimestamp(plan.created_at)}
          </time>
        </div>
      </Link>
    </li>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <section className={styles.state}>
      <p role="status">{label}</p>
    </section>
  );
}

function EmptyState({ hasActiveFilters }: { hasActiveFilters: boolean }) {
  const title = hasActiveFilters
    ? planCopy.list.emptyTitle
    : planCopy.list.noPlansTitle;
  const body = hasActiveFilters
    ? planCopy.list.emptyBody
    : planCopy.list.noPlansBody;

  return (
    <section className={styles.state}>
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}

function sumActionTypeCounts(
  counts: PlanSummary["summary"]["counts"]["blocked"],
) {
  return counts.move + counts.skip + counts.refresh_metadata;
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.valueOf())
    ? value
    : timestampFormatter.format(timestamp);
}
