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
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";
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
const numberFormatter = new Intl.NumberFormat("en-US");

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
      <PageHeader
        description={planCopy.list.description}
        eyebrow={planCopy.list.eyebrow}
        title={planCopy.list.title}
      />

      <form
        aria-label="Plan filters"
        className={toolbarStyles.toolbar}
        onSubmit={(event) => event.preventDefault()}
      >
        <label className={toolbarStyles.search} htmlFor="plan-search">
          <VisuallyHidden>{planCopy.list.searchLabel}</VisuallyHidden>
          <input
            autoComplete="off"
            data-list-search
            id="plan-search"
            name="plan-search"
            onChange={(event) => updateFilters({ query: event.target.value })}
            placeholder={planCopy.list.searchPlaceholder}
            type="search"
            value={filters.query}
          />
        </label>
        <label className={toolbarStyles.control} htmlFor="plan-status">
          <VisuallyHidden>{planCopy.list.statusLabel}</VisuallyHidden>
          <select
            id="plan-status"
            name="plan-status"
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
        </label>
        <label className={toolbarStyles.control} htmlFor="plan-type">
          <VisuallyHidden>{planCopy.list.typeLabel}</VisuallyHidden>
          <select
            id="plan-type"
            name="plan-type"
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
        </label>
        <label className={toolbarStyles.checkbox}>
          <input
            checked={filters.blocked}
            name="plan-blocked"
            onChange={(event) =>
              updateFilters({ blocked: event.target.checked })
            }
            type="checkbox"
          />
          {planCopy.list.blockedLabel}
        </label>
        <div className={toolbarStyles.actions}>
          {hasActiveFilters ? (
            <Button onClick={resetFilters} variant="quiet">
              {planCopy.list.resetFilters}
            </Button>
          ) : null}
          {query.data !== undefined ? (
            <p aria-live="polite" className={toolbarStyles.resultCount}>
              {numberFormatter.format(total)} {planCopy.list.resultCount}
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
          <li aria-hidden="true" className={styles.planColumnHeader}>
            <span>Type</span>
            <span>Plan ID</span>
            <span>Actions</span>
            <span>Blocked</span>
            <span>Status</span>
            <span>Created</span>
          </li>
          {plans.map((plan) => (
            <PlanRow key={plan.plan_id} plan={plan} search={location.search} />
          ))}
        </ul>
      ) : null}
      {query.isSuccess && plans.length > 0 && cursorPage.page !== undefined ? (
        <CursorPageControls
          collectionLabel="Plans"
          pageSize={cursorPage.page.page.limit}
          totalItems={cursorPage.page.page.total}
          {...cursorPage}
        />
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
        <span className={styles.planType}>
          <PlanTypeValue value={plan.plan_type} />
        </span>
        <code
          className={`${styles.id} ${styles.planIdentifier}`}
          title={plan.plan_id}
          translate="no"
        >
          {plan.plan_id}
        </code>
        <span className={styles.planActions}>
          <VisuallyHidden>{planCopy.detail.actionCount}: </VisuallyHidden>
          {numberFormatter.format(plan.summary.total)}
        </span>
        <span className={styles.planBlocked}>
          <VisuallyHidden>{planCopy.labels.blocked}: </VisuallyHidden>
          {numberFormatter.format(blockedCount)}
        </span>
        <span className={styles.planStatus}>
          <PlanStatusBadge value={plan.status} />
        </span>
        <time
          className={styles.planCreated}
          dateTime={plan.created_at}
          title={formatTimestamp(plan.created_at)}
        >
          {formatTimestamp(plan.created_at)}
        </time>
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
