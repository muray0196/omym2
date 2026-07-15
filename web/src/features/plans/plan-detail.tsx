/**
 * Summary: Renders one Plan review with exact capabilities and recorded action evidence.
 * Why: Keeps execution controls beside the immutable Plan data they act on.
 */
import {
  type InfiniteData,
  useInfiniteQuery,
  useQuery,
  type UseInfiniteQueryResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useDeferredValue } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { useCursorPage } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";
import { planCopy } from "./plan-copy";
import { PlanErrorState } from "./plan-error-state";
import { PlanExecutionControls } from "./plan-execution-controls";
import {
  actionGroupValueLabel,
  actionGroupingLabel,
  actionStatusLabel,
  actionTypeLabel,
  reasonLabel,
} from "./plan-catalog";
import {
  ActionStatusBadge,
  ActionTypeValue,
  PlanStatusBadge,
  PlanTypeValue,
  ReasonValue,
} from "./plan-presentation";
import {
  exactPlanQuery,
  planActionFacetsQuery,
  planActionGroupsInfiniteQuery,
  planActionsInfiniteQuery,
  PlansApiError,
  type PlanAction,
  type PlanActionFacets,
  type PlanActionGroups,
  type PlanActionPage,
  type PlanDetail,
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
  const location = useLocation();
  const planId = routePlanId ?? "";
  const { clearGroup, filters, hasActiveFilters, resetFilters, updateFilters } =
    usePlanActionFilters();
  const deferredQuery = useDeferredValue(filters.query);
  const queryFilters = { ...filters, query: deferredQuery };
  const exactPlan = useQuery(exactPlanQuery(planId));
  const actions = useInfiniteQuery(
    planActionsInfiniteQuery(planId, queryFilters),
  );
  const facets = useQuery(planActionFacetsQuery(planId, queryFilters));
  const groups = useInfiniteQuery(
    planActionGroupsInfiniteQuery(planId, queryFilters),
  );
  const paginationResetKey = JSON.stringify({ planId, ...queryFilters });
  if (planId.length === 0) {
    return <NotFoundState />;
  }

  const planNotFound = exactPlan.isError && isPlanNotFound(exactPlan.error);

  return (
    <article className={styles.page}>
      <div className={styles.backLinkRow}>
        <Link
          className={styles.backLink}
          data-detail-back
          to={{ pathname: "/plans", search: location.search }}
        >
          {planCopy.detail.back}
        </Link>
      </div>
      <PageHeader
        eyebrow={planCopy.detail.eyebrow}
        title={
          planNotFound ? planCopy.detail.notFoundTitle : planCopy.detail.title
        }
      />
      {exactPlan.isSuccess ? <PlanMetadata plan={exactPlan.data.plan} /> : null}

      {exactPlan.isPending ? (
        <section className={styles.state}>
          <p role="status">{planCopy.detail.loading}</p>
        </section>
      ) : exactPlan.isError ? (
        planNotFound ? (
          <section className={styles.state}>
            <p>{planCopy.detail.notFoundBody}</p>
          </section>
        ) : (
          <PlanErrorState
            error={exactPlan.error}
            onRetry={() => void exactPlan.refetch()}
            retryLabel={planCopy.detail.retry}
            title={planCopy.detail.loadError}
          />
        )
      ) : (
        <>
          <PlanSummaryTable summary={exactPlan.data.summary} />
          <PlanExecutionControls detail={exactPlan.data} />

          <ActionFilters
            clearGroup={clearGroup}
            filters={filters}
            hasActiveFilters={hasActiveFilters}
            onReset={resetFilters}
            onUpdate={updateFilters}
          />

          <ActionListSection actions={actions} resetKey={paginationResetKey} />
          <FacetSection facets={facets} />
          <GroupSection
            filters={filters}
            groups={groups}
            onUpdate={updateFilters}
            resetKey={paginationResetKey}
          />
        </>
      )}
    </article>
  );
}

function PlanMetadata({ plan }: { plan: PlanDetail["plan"] }) {
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
        <dd>
          <PlanTypeValue value={plan.plan_type} />
        </dd>
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

function PlanSummaryTable({ summary }: { summary: PlanDetail["summary"] }) {
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
      aria-label="Plan action filters"
      className={toolbarStyles.toolbar}
      onSubmit={(event) => event.preventDefault()}
    >
      <label className={toolbarStyles.search} htmlFor="action-search">
        <VisuallyHidden>{planCopy.detail.actionSearchLabel}</VisuallyHidden>
        <input
          autoComplete="off"
          data-list-search
          id="action-search"
          name="action-search"
          onChange={(event) => onUpdate({ query: event.target.value })}
          placeholder={planCopy.detail.actionSearchPlaceholder}
          type="search"
          value={filters.query}
        />
      </label>
      <SelectField
        id="action-status"
        label={planCopy.detail.actionStatusLabel}
        onChange={(value) =>
          onUpdate({
            status: actionStatusOptions.find((option) => option.value === value)
              ?.value,
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
            reason: actionReasonOptions.find((option) => option.value === value)
              ?.value,
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
      <div className={toolbarStyles.actions}>
        {hasActiveFilters ? (
          <Button onClick={onReset} variant="quiet">
            {planCopy.detail.clearActionFilters}
          </Button>
        ) : null}
      </div>
      {filters.groupKey !== undefined ? (
        <div className={toolbarStyles.secondaryRow}>
          <p className={toolbarStyles.selected}>
            {planCopy.detail.selectedGroup}:{" "}
            {actionGroupValueLabel(
              filters.groupBy,
              filters.groupKey,
              filters.groupKey,
            )}
          </p>
          <Button onClick={clearGroup} variant="quiet">
            {planCopy.detail.clearGroup}
          </Button>
        </div>
      ) : null}
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
    <label className={toolbarStyles.control} htmlFor={id}>
      <VisuallyHidden>{label}</VisuallyHidden>
      <select
        id={id}
        name={id}
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
    </label>
  );
}

function ActionListSection({
  actions,
  resetKey,
}: {
  actions: UseInfiniteQueryResult<
    InfiniteData<PlanActionPage, string | undefined>,
    Error
  >;
  resetKey: string;
}) {
  const actionPage = useCursorPage({
    fetchNextPage: actions.fetchNextPage,
    hasNextPage: actions.hasNextPage,
    isFetchingNextPage: actions.isFetchingNextPage,
    pages: actions.data?.pages,
    resetKey,
  });
  const actionItems = actionPage.page?.items ?? [];

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
          <CursorPageControls
            collectionLabel="Plan actions"
            pageSize={actionPage.page?.page.limit}
            totalItems={actionPage.page?.page.total}
            {...actionPage}
          />
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
        <ActionTypeValue value={action.action_type} />
        <ReasonValue value={action.reason} />
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
      {action.artist_name_diagnostics !== null ? (
        <ArtistNameDiagnostics diagnostics={action.artist_name_diagnostics} />
      ) : null}
    </li>
  );
}

type ArtistNameDiagnosticsValue = NonNullable<
  PlanAction["artist_name_diagnostics"]
>;

type ArtistNameDiagnosticValue = ArtistNameDiagnosticsValue["artist"];

function ArtistNameDiagnostics({
  diagnostics,
}: {
  diagnostics: ArtistNameDiagnosticsValue;
}) {
  return (
    <section className={styles.artistNameDiagnostics}>
      <h3>{planCopy.detail.artistNameDiagnostics}</h3>
      <dl className={styles.artistNameDiagnosticList}>
        <ArtistNameDiagnostic
          diagnostic={diagnostics.artist}
          fieldLabel={planCopy.labels.artist}
        />
        <ArtistNameDiagnostic
          diagnostic={diagnostics.album_artist}
          fieldLabel={planCopy.labels.albumArtist}
        />
      </dl>
    </section>
  );
}

function ArtistNameDiagnostic({
  diagnostic,
  fieldLabel,
}: {
  diagnostic: ArtistNameDiagnosticValue;
  fieldLabel: string;
}) {
  return (
    <div className={styles.artistNameDiagnostic}>
      <dt>{fieldLabel}</dt>
      <dd>
        <div className={styles.artistNameResolution}>
          <code>{diagnostic.source_name ?? "—"}</code>
          <VisuallyHidden> resolves to </VisuallyHidden>
          <span aria-hidden="true" className={styles.artistNameArrow}>
            →
          </span>
          <code>{diagnostic.resolved_name ?? "—"}</code>
        </div>
        <div className={styles.artistNameDiagnosticMetadata}>
          <span>
            <strong>{planCopy.labels.provenance}:</strong>{" "}
            {artistNameProvenanceLabel(diagnostic.provenance)}
          </span>
          <span>
            <strong>{planCopy.labels.issue}:</strong>{" "}
            {diagnostic.issue === null
              ? planCopy.artistNames.noIssue
              : artistNameIssueLabel(diagnostic.issue)}
          </span>
        </div>
      </dd>
    </div>
  );
}

function artistNameProvenanceLabel(value: string): string {
  const labels: Record<string, string> = planCopy.artistNames.provenance;
  return labels[value] ?? `${planCopy.unknown.artistNameProvenance}: ${value}`;
}

function artistNameIssueLabel(value: string): string {
  const labels: Record<string, string> = planCopy.artistNames.issue;
  return labels[value] ?? `${planCopy.unknown.artistNameIssue}: ${value}`;
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
  resetKey,
}: {
  filters: PlanActionFilters;
  groups: UseInfiniteQueryResult<
    InfiniteData<PlanActionGroups, string | undefined>,
    Error
  >;
  onUpdate: (changes: Partial<PlanActionFilters>) => void;
  resetKey: string;
}) {
  const groupPage = useCursorPage({
    fetchNextPage: groups.fetchNextPage,
    hasNextPage: groups.hasNextPage,
    isFetchingNextPage: groups.isFetchingNextPage,
    pages: groups.data?.pages,
    resetKey,
  });
  const groupItems = groupPage.page?.items ?? [];

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
                  <span className={styles.groupValue}>
                    {actionGroupValueLabel(
                      groupPage.page?.group_by ?? filters.groupBy,
                      group.key,
                      group.label,
                    )}
                  </span>
                  <span className={styles.subtle}>
                    {group.blocked_count} {planCopy.labels.blocked} ·{" "}
                    {planCopy.labels.topReason}: {reasonLabel(group.top_reason)}
                  </span>
                </button>
                <span className={styles.count}>{group.count}</span>
              </li>
            ))}
          </ul>
          <CursorPageControls
            collectionLabel="Plan action groups"
            pageSize={groupPage.page?.page.limit}
            totalItems={groupPage.page?.page.total}
            {...groupPage}
          />
        </>
      ) : null}
    </section>
  );
}

function NotFoundState() {
  return (
    <article className={styles.page}>
      <div className={styles.backLinkRow}>
        <Link className={styles.backLink} data-detail-back to="/plans">
          {planCopy.detail.back}
        </Link>
      </div>
      <PageHeader
        eyebrow={planCopy.detail.eyebrow}
        title={planCopy.detail.notFoundTitle}
      />
      <section className={styles.state}>
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
