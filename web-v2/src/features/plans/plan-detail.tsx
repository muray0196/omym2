/**
 * Summary: Renders a read-only deep inspection view for one recorded Plan.
 * Why: Exposes stored actions, facets, and opaque group drill-downs without operation controls.
 */
import {
  type InfiniteData,
  useInfiniteQuery,
  useQuery,
  type UseInfiniteQueryResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Button } from "../../ui/primitives/button";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { planCopy } from "./plan-copy";
import { PlanErrorState } from "./plan-error-state";
import {
  actionGroupingLabel,
  actionStatusLabel,
  actionTypeLabel,
  planTypeLabel,
  reasonLabel,
} from "./plan-catalog";
import { ActionStatusBadge, PlanStatusBadge } from "./plan-presentation";
import {
  exactPlanListQuery,
  planActionFacetsQuery,
  planActionGroupsInfiniteQuery,
  planActionsInfiniteQuery,
  PlansApiError,
  type PlanAction,
  type PlanActionFacets,
  type PlanActionGroups,
  type PlanActionPage,
  type PlanSummary,
} from "./plan-query";
import {
  actionGroupingOptions,
  actionReasonOptions,
  actionStatusOptions,
  actionTypeOptions,
  type PlanActionFilters,
  usePlanActionFilters,
} from "./plan-url-state";
import styles from "./plan-inspection.module.css";

const timestampFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

type FacetValues =
  | PlanActionFacets["facets"]["status"]
  | PlanActionFacets["facets"]["action_type"]
  | PlanActionFacets["facets"]["reason"];

type FacetValue = FacetValues[number];

export function PlanDetail() {
  const { planId: routePlanId } = useParams();
  const planId = routePlanId ?? "";
  const { clearGroup, filters, hasActiveFilters, resetFilters, updateFilters } =
    usePlanActionFilters();
  const exactPlan = useQuery(exactPlanListQuery(planId));
  const actions = useInfiniteQuery(planActionsInfiniteQuery(planId, filters));
  const facets = useQuery(planActionFacetsQuery(planId, filters));
  const groups = useInfiniteQuery(
    planActionGroupsInfiniteQuery(planId, filters),
  );
  if (planId.length === 0) {
    return <NotFoundState />;
  }

  if (exactPlan.isPending) {
    return <LoadingDetailState />;
  }

  if (exactPlan.isError) {
    if (isPlanNotFound(exactPlan.error)) {
      return <NotFoundState />;
    }
    return (
      <PlanErrorState
        error={exactPlan.error}
        onRetry={() => void exactPlan.refetch()}
        retryLabel={planCopy.detail.retry}
        title={planCopy.detail.loadError}
      />
    );
  }

  const plan = exactPlan.data.items.find((item) => item.plan_id === planId);

  if (plan === undefined) {
    return <NotFoundState />;
  }

  return (
    <article className={styles.page}>
      <div className={styles.backLinkRow}>
        <Link className={styles.backLink} to="/plans">
          {planCopy.detail.back}
        </Link>
      </div>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{planCopy.detail.eyebrow}</p>
        <RouteHeading>{planCopy.detail.title}</RouteHeading>
        <PlanMetadata plan={plan} />
      </header>

      <PlanSummaryTable summary={plan.summary} />

      <ActionFilters
        clearGroup={clearGroup}
        filters={filters}
        hasActiveFilters={hasActiveFilters}
        onReset={resetFilters}
        onUpdate={updateFilters}
      />

      <ActionListSection actions={actions} />
      <FacetSection facets={facets} />
      <GroupSection
        filters={filters}
        groups={groups}
        onUpdate={updateFilters}
      />
    </article>
  );
}

function PlanMetadata({ plan }: { plan: PlanSummary }) {
  return (
    <dl className={styles.metadataList}>
      <div>
        <dt>{planCopy.labels.identifier}</dt>
        <dd className={styles.metadataValue}>{plan.plan_id}</dd>
      </div>
      <div>
        <dt>{planCopy.labels.library}</dt>
        <dd className={styles.metadataValue}>{plan.library_id}</dd>
      </div>
      <div>
        <dt>{planCopy.labels.created}</dt>
        <dd>
          <time dateTime={plan.created_at}>
            {formatTimestamp(plan.created_at)}
          </time>
        </dd>
      </div>
      <div>
        <dt>{planCopy.labels.type}</dt>
        <dd>{planTypeLabel(plan.plan_type)}</dd>
      </div>
      <div>
        <dt>{planCopy.labels.status}</dt>
        <dd>
          <PlanStatusBadge value={plan.status} />
        </dd>
      </div>
    </dl>
  );
}

function PlanSummaryTable({ summary }: { summary: PlanSummary["summary"] }) {
  const rows = [
    { counts: summary.counts.planned, label: planCopy.labels.planned },
    { counts: summary.counts.blocked, label: planCopy.labels.blocked },
    { counts: summary.counts.applied, label: planCopy.labels.applied },
    { counts: summary.counts.failed, label: planCopy.labels.failed },
  ];

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2>{planCopy.detail.summary}</h2>
        <p className={styles.subtle}>
          {summary.total} {planCopy.detail.actionCount}
        </p>
      </div>
      <div className={styles.summaryTableWrap}>
        <table className={styles.summaryTable}>
          <caption>{planCopy.detail.summary}</caption>
          <thead>
            <tr>
              <th scope="col">{planCopy.labels.status}</th>
              <th scope="col">{planCopy.labels.move}</th>
              <th scope="col">{planCopy.labels.skip}</th>
              <th scope="col">{planCopy.labels.refreshMetadata}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td>{row.counts.move}</td>
                <td>{row.counts.skip}</td>
                <td>{row.counts.refresh_metadata}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ActionFilters({
  clearGroup,
  filters,
  hasActiveFilters,
  onReset,
  onUpdate,
}: {
  clearGroup: () => void;
  filters: PlanActionFilters;
  hasActiveFilters: boolean;
  onReset: () => void;
  onUpdate: (changes: Partial<PlanActionFilters>) => void;
}) {
  return (
    <form
      className={styles.filterPanel}
      onSubmit={(event) => event.preventDefault()}
    >
      <div className={styles.filterGrid}>
        <div className={styles.field}>
          <label htmlFor="action-search">
            {planCopy.detail.actionSearchLabel}
          </label>
          <input
            id="action-search"
            onChange={(event) => onUpdate({ query: event.target.value })}
            placeholder={planCopy.detail.actionSearchPlaceholder}
            type="search"
            value={filters.query}
          />
        </div>
        <SelectField
          id="action-status"
          label={planCopy.detail.actionStatusLabel}
          onChange={(value) =>
            onUpdate({
              status: actionStatusOptions.find(
                (option) => option.value === value,
              )?.value,
            })
          }
          options={actionStatusOptions}
          placeholder={planCopy.detail.allActionStatuses}
          value={filters.status ?? ""}
        />
        <SelectField
          id="action-type"
          label={planCopy.detail.actionTypeLabel}
          onChange={(value) =>
            onUpdate({
              actionType: actionTypeOptions.find(
                (option) => option.value === value,
              )?.value,
            })
          }
          options={actionTypeOptions}
          placeholder={planCopy.detail.allActionTypes}
          value={filters.actionType ?? ""}
        />
        <SelectField
          id="action-reason"
          label={planCopy.detail.reasonLabel}
          onChange={(value) =>
            onUpdate({
              reason: actionReasonOptions.find(
                (option) => option.value === value,
              )?.value,
            })
          }
          options={actionReasonOptions}
          placeholder={planCopy.detail.allReasons}
          value={filters.reason ?? ""}
        />
        <SelectField
          id="action-grouping"
          label={planCopy.detail.groupingLabel}
          onChange={(value) =>
            onUpdate({
              groupBy: actionGroupingOptions.find(
                (option) => option.value === value,
              )?.value,
              groupKey: undefined,
            })
          }
          options={actionGroupingOptions}
          placeholder={planCopy.detail.groupingLabel}
          value={filters.groupBy}
        />
      </div>
      <div className={styles.filterActions}>
        {hasActiveFilters ? (
          <Button onClick={onReset} variant="quiet">
            {planCopy.detail.clearActionFilters}
          </Button>
        ) : null}
        {filters.groupKey !== undefined ? (
          <>
            <p className={styles.selectedGroup}>
              {planCopy.detail.selectedGroup}: {filters.groupKey}
            </p>
            <Button onClick={clearGroup} variant="quiet">
              {planCopy.detail.clearGroup}
            </Button>
          </>
        ) : null}
      </div>
    </form>
  );
}

function SelectField({
  id,
  label,
  onChange,
  options,
  placeholder,
  value,
}: {
  id: string;
  label: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<{ label: string; value: string }>;
  placeholder: string;
  value: string;
}) {
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ActionListSection({
  actions,
}: {
  actions: UseInfiniteQueryResult<
    InfiniteData<PlanActionPage, string | undefined>,
    Error
  >;
}) {
  const actionItems = actions.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2>{planCopy.detail.actions}</h2>
        {actions.data !== undefined ? (
          <p className={styles.subtle}>
            {actions.data.pages.at(-1)?.page.total ?? 0}{" "}
            {planCopy.detail.actionCount}
          </p>
        ) : null}
      </div>
      {actions.isPending ? (
        <p role="status">{planCopy.detail.loadingActions}</p>
      ) : null}
      {actions.isError ? (
        <PlanErrorState
          error={actions.error}
          onRetry={() => void actions.refetch()}
          retryLabel={planCopy.detail.retry}
          title={planCopy.detail.loadError}
        />
      ) : null}
      {actions.isSuccess && actionItems.length === 0 ? (
        <p className={styles.subtle}>{planCopy.detail.noActions}</p>
      ) : null}
      {actions.isSuccess && actionItems.length > 0 ? (
        <>
          <ul
            aria-label={planCopy.detail.actions}
            className={styles.actionList}
          >
            {actionItems.map((action) => (
              <ActionRow action={action} key={action.action_id} />
            ))}
          </ul>
          {actions.hasNextPage ? (
            <div className={styles.loadMoreArea}>
              {actions.isFetchingNextPage ? (
                <p aria-live="polite" className={styles.subtle} role="status">
                  {planCopy.detail.loadingMoreActions}
                </p>
              ) : null}
              <Button
                disabled={actions.isFetchingNextPage}
                onClick={() => void actions.fetchNextPage()}
                variant="secondary"
              >
                {planCopy.detail.loadMoreActions}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function ActionRow({ action }: { action: PlanAction }) {
  return (
    <li className={styles.actionRow}>
      <div className={styles.actionHeader}>
        <code className={styles.id}>{action.action_id}</code>
        <ActionStatusBadge value={action.status} />
      </div>
      <div className={styles.actionMetadata}>
        <span>{actionTypeLabel(action.action_type)}</span>
        <span>{reasonLabel(action.reason)}</span>
        <span>
          {planCopy.labels.trackId}: {action.track_id ?? "—"}
        </span>
      </div>
      <dl className={styles.pathList}>
        <div className={styles.pathItem}>
          <dt className={styles.pathLabel}>{planCopy.labels.sourcePath}</dt>
          <dd className={styles.path}>{action.source_path ?? "—"}</dd>
        </div>
        <div className={styles.pathItem}>
          <dt className={styles.pathLabel}>{planCopy.labels.targetPath}</dt>
          <dd className={styles.path}>{action.target_path ?? "—"}</dd>
        </div>
      </dl>
    </li>
  );
}

function FacetSection({
  facets,
}: {
  facets: UseQueryResult<PlanActionFacets, Error>;
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2>{planCopy.detail.facets}</h2>
        {facets.data !== undefined ? (
          <p className={styles.subtle}>
            {facets.data.target_collisions} {planCopy.detail.targetCollisions}
          </p>
        ) : null}
      </div>
      {facets.isPending ? (
        <p role="status">{planCopy.detail.loadingFacets}</p>
      ) : null}
      {facets.isError ? (
        <PlanErrorState
          error={facets.error}
          onRetry={() => void facets.refetch()}
          retryLabel={planCopy.detail.retry}
          title={planCopy.detail.loadError}
        />
      ) : null}
      {facets.isSuccess ? <FacetRows data={facets.data} /> : null}
    </section>
  );
}

function FacetRows({ data }: { data: PlanActionFacets }) {
  const sections = [
    {
      label: planCopy.labels.status,
      values: data.facets.status,
      format: actionStatusLabel,
    },
    {
      label: planCopy.labels.actionType,
      values: data.facets.action_type,
      format: actionTypeLabel,
    },
    {
      label: planCopy.labels.reason,
      values: data.facets.reason,
      format: (value: string) => reasonLabel(value),
    },
  ] as const;

  if (sections.every((section) => section.values.length === 0)) {
    return <p className={styles.subtle}>{planCopy.detail.noFacets}</p>;
  }

  return (
    <div className={styles.cards}>
      {sections.map((section) => (
        <section className={styles.card} key={section.label}>
          <h3>{section.label}</h3>
          <FacetValueRows format={section.format} values={section.values} />
        </section>
      ))}
    </div>
  );
}

function FacetValueRows({
  format,
  values,
}: {
  format: (value: FacetValue["value"]) => string;
  values: FacetValues;
}) {
  return (
    <ul className={styles.facetList}>
      {values.map((facet) => (
        <li className={styles.facetRow} key={facet.value}>
          <span className={styles.facetValue}>{format(facet.value)}</span>
          <span className={styles.count}>{facet.count}</span>
        </li>
      ))}
    </ul>
  );
}

function GroupSection({
  filters,
  groups,
  onUpdate,
}: {
  filters: PlanActionFilters;
  groups: UseInfiniteQueryResult<
    InfiniteData<PlanActionGroups, string | undefined>,
    Error
  >;
  onUpdate: (changes: Partial<PlanActionFilters>) => void;
}) {
  const groupItems = groups.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2>{planCopy.detail.actionGroups}</h2>
        <p className={styles.subtle}>{actionGroupingLabel(filters.groupBy)}</p>
      </div>
      {groups.isPending ? (
        <p role="status">{planCopy.detail.loadingGroups}</p>
      ) : null}
      {groups.isError ? (
        <PlanErrorState
          error={groups.error}
          onRetry={() => void groups.refetch()}
          retryLabel={planCopy.detail.retry}
          title={planCopy.detail.loadError}
        />
      ) : null}
      {groups.isSuccess && groupItems.length === 0 ? (
        <p className={styles.subtle}>{planCopy.detail.noGroups}</p>
      ) : null}
      {groups.isSuccess && groupItems.length > 0 ? (
        <>
          <ul
            aria-label={planCopy.detail.actionGroups}
            className={styles.groupList}
          >
            {groupItems.map((group) => (
              <li className={styles.groupRow} key={group.key}>
                <button
                  aria-pressed={filters.groupKey === group.key}
                  className={styles.groupButton}
                  onClick={() => onUpdate({ groupKey: group.key })}
                  type="button"
                >
                  <span className={styles.groupValue}>{group.label}</span>
                  <span className={styles.subtle}>
                    {group.blocked_count} {planCopy.labels.blocked} ·{" "}
                    {planCopy.labels.topReason}: {reasonLabel(group.top_reason)}
                  </span>
                </button>
                <span className={styles.count}>{group.count}</span>
              </li>
            ))}
          </ul>
          {groups.hasNextPage ? (
            <div className={styles.loadMoreArea}>
              {groups.isFetchingNextPage ? (
                <p aria-live="polite" className={styles.subtle} role="status">
                  {planCopy.detail.loadingMoreGroups}
                </p>
              ) : null}
              <Button
                disabled={groups.isFetchingNextPage}
                onClick={() => void groups.fetchNextPage()}
                variant="secondary"
              >
                {planCopy.detail.loadMoreGroups}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function LoadingDetailState() {
  return (
    <article className={styles.page}>
      <section className={styles.state}>
        <p role="status">{planCopy.detail.loading}</p>
      </section>
    </article>
  );
}

function NotFoundState() {
  return (
    <article className={styles.page}>
      <div className={styles.backLinkRow}>
        <Link className={styles.backLink} to="/plans">
          {planCopy.detail.back}
        </Link>
      </div>
      <section className={styles.state}>
        <RouteHeading>{planCopy.detail.notFoundTitle}</RouteHeading>
        <p>{planCopy.detail.notFoundBody}</p>
      </section>
    </article>
  );
}

function isPlanNotFound(error: Error) {
  return (
    error instanceof PlansApiError &&
    error.envelope.errors.some((item) => item.code === "plan_not_found")
  );
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.valueOf())
    ? value
    : timestampFormatter.format(timestamp);
}
