/**
 * Summary: Renders one Run with durable evidence and backend-authoritative Undo planning.
 * Why: Keeps reversal generation reviewable while preserving partial and unknown outcomes.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";

import {
  eventStatusLabel,
  formatTimestamp,
} from "../../features/history/history-catalog";
import { historyCopy } from "../../features/history/history-copy";
import {
  EventStatusBadge,
  EventTypeValue,
  RunStatusBadge,
} from "../../features/history/history-presentation";
import {
  runDetailQuery,
  runEventFacetsQuery,
  runEventGroupsInfiniteQuery,
  runEventsInfiniteQuery,
} from "../../features/history/history-query";
import { UndoPlanControl } from "../../features/history/undo-plan-control";
import {
  eventStatusOptions,
  useEventFilters,
} from "../../features/history/history-url-state";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import styles from "../../features/inspection/inspection.module.css";
import { InspectionApiError } from "../../features/inspection/query-errors";
import { useCursorPage } from "../../ui/cursor-page";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";

const numberFormatter = new Intl.NumberFormat("en-US");

export function Component() {
  const { runId = "" } = useParams();
  const location = useLocation();
  const { filters, updateFilters } = useEventFilters();
  const detailQuery = useQuery(runDetailQuery(runId));
  const eventsQuery = useInfiniteQuery(runEventsInfiniteQuery(runId, filters));
  const facetsQuery = useQuery(runEventFacetsQuery(runId));
  const groupsQuery = useInfiniteQuery(runEventGroupsInfiniteQuery(runId));
  const eventPage = useCursorPage({
    fetchNextPage: eventsQuery.fetchNextPage,
    hasNextPage: eventsQuery.hasNextPage,
    isFetchingNextPage: eventsQuery.isFetchingNextPage,
    pages: eventsQuery.data?.pages,
    resetKey: JSON.stringify({ runId, ...filters }),
  });
  const groupPage = useCursorPage({
    fetchNextPage: groupsQuery.fetchNextPage,
    hasNextPage: groupsQuery.hasNextPage,
    isFetchingNextPage: groupsQuery.isFetchingNextPage,
    pages: groupsQuery.data?.pages,
    resetKey: runId,
  });
  const isNotFound =
    detailQuery.isError &&
    detailQuery.error instanceof InspectionApiError &&
    detailQuery.error.envelope.errors.some(
      (error) => error.code === "run_not_found",
    );
  const detail = detailQuery.data;
  const events = eventPage.page?.items ?? [];
  const groups = groupPage.page?.items ?? [];
  const run = detail?.run;

  return (
    <article className={styles.page}>
      <Link
        className={styles.backLink}
        data-detail-back
        to={{ pathname: "/history", search: location.search }}
      >
        {historyCopy.detail.back}
      </Link>
      <PageHeader
        description={
          detailQuery.isSuccess ? (
            <code className={styles.id} translate="no">
              {detailQuery.data.run.run_id}
            </code>
          ) : undefined
        }
        eyebrow={historyCopy.detail.eyebrow}
        title={historyCopy.detail.title}
      />
      {detailQuery.isPending ? (
        <section className={styles.state} role="status">
          {historyCopy.detail.loading}
        </section>
      ) : detailQuery.isError ? (
        isNotFound ? (
          <section className={styles.state}>
            <p>{historyCopy.detail.notFound}</p>
          </section>
        ) : (
          <InspectionErrorState
            error={detailQuery.error}
            onRetry={() => void detailQuery.refetch()}
            title={historyCopy.detail.error}
          />
        )
      ) : detail !== undefined && run !== undefined ? (
        <>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>{historyCopy.detail.metadata}</h2>
              <RunStatusBadge value={run.status} />
            </div>
            <dl className={styles.metadataList}>
              <div>
                <dt>{historyCopy.labels.planId}</dt>
                <dd className={styles.id}>{run.plan_id}</dd>
              </div>
              <div>
                <dt>{historyCopy.labels.libraryId}</dt>
                <dd className={styles.id}>{run.library_id}</dd>
              </div>
              <div>
                <dt>{historyCopy.labels.started}</dt>
                <dd>{formatTimestamp(run.started_at)}</dd>
              </div>
              <div>
                <dt>{historyCopy.labels.completed}</dt>
                <dd>{formatTimestamp(run.completed_at)}</dd>
              </div>
            </dl>
            {run.error_summary ? (
              <div className={styles.warning}>
                <strong>{historyCopy.labels.error}</strong>
                <p>{run.error_summary}</p>
              </div>
            ) : null}
          </section>
          <UndoPlanControl detail={detail} />
          <section
            className={toolbarStyles.toolbar}
            aria-label="FileEvent filters"
          >
            <label className={toolbarStyles.control}>
              <VisuallyHidden>Event status</VisuallyHidden>
              <select
                name="event-status"
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
                <option value="">All event statuses</option>
                {eventStatusOptions.map((status) => (
                  <option key={status} value={status}>
                    {eventStatusLabel(status)}
                  </option>
                ))}
              </select>
            </label>
          </section>
          {facetsQuery.data ? (
            <section className={styles.section}>
              <h2>{historyCopy.detail.facets}</h2>
              <ul className={styles.facetList}>
                {facetsQuery.data.facets.status.map((facet) => (
                  <li className={styles.facet} key={facet.value}>
                    <EventStatusBadge value={facet.value} />
                    <span className={styles.count}>
                      {numberFormatter.format(facet.count)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {groupsQuery.data ? (
            <section className={styles.section}>
              <h2>{historyCopy.detail.groups}</h2>
              {groups.length === 0 ? (
                <p>No target-directory groups were recorded.</p>
              ) : (
                <ul className={styles.groupList}>
                  {groups.map((group) => (
                    <li className={styles.group} key={group.key}>
                      <span className={styles.path}>{group.label}</span>
                      <span className={styles.count}>
                        {numberFormatter.format(group.count)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {groups.length > 0 ? (
                <CursorPageControls
                  collectionLabel="FileEvent groups"
                  pageSize={groupPage.page?.page.limit}
                  totalItems={groupPage.page?.page.total}
                  {...groupPage}
                />
              ) : null}
            </section>
          ) : null}
          <section className={styles.section}>
            <h2>{historyCopy.detail.events}</h2>
            {eventsQuery.isPending ? (
              <p role="status">Loading FileEvents…</p>
            ) : null}
            {eventsQuery.isError ? (
              <InspectionErrorState
                error={eventsQuery.error}
                onRetry={() => void eventsQuery.refetch()}
                title="FileEvents could not be loaded"
              />
            ) : null}
            {eventsQuery.isSuccess && events.length === 0 ? (
              <p>{historyCopy.detail.noEvents}</p>
            ) : null}
            {events.length > 0 ? (
              <ol className={styles.list}>
                {events.map((event) => (
                  <li className={styles.row} key={event.event_id}>
                    <div className={styles.rowHeader}>
                      <span className={styles.id}>{event.event_id}</span>
                      <EventStatusBadge value={event.status} />
                    </div>
                    <p>
                      <EventTypeValue value={event.event_type} /> · sequence{" "}
                      {numberFormatter.format(event.sequence_no)}
                    </p>
                    <dl className={styles.metadataList}>
                      <div>
                        <dt>{historyCopy.labels.actionId}</dt>
                        <dd className={styles.id}>{event.plan_action_id}</dd>
                      </div>
                      {event.companion_asset_id !== null ? (
                        <div>
                          <dt>{historyCopy.labels.companionAssetId}</dt>
                          <dd className={styles.id}>
                            {event.companion_asset_id}
                          </dd>
                        </div>
                      ) : null}
                      <div>
                        <dt>{historyCopy.labels.source}</dt>
                        <dd className={styles.path}>{event.source_path}</dd>
                      </div>
                      <div>
                        <dt>{historyCopy.labels.target}</dt>
                        <dd className={styles.path}>{event.target_path}</dd>
                      </div>
                    </dl>
                    {event.status === "pending" ? (
                      <div className={styles.warning}>
                        <strong>Manual review required</strong>
                        <p>{historyCopy.pending}</p>
                      </div>
                    ) : null}
                    {event.error_code || event.error_message ? (
                      <p>
                        {event.error_code ?? historyCopy.unknown.errorCode}:{" "}
                        {event.error_message ?? "No recorded detail"}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : null}
            {eventsQuery.isSuccess &&
            events.length > 0 &&
            eventPage.page !== undefined ? (
              <CursorPageControls
                collectionLabel="FileEvents"
                pageSize={eventPage.page.page.limit}
                totalItems={eventPage.page.page.total}
                {...eventPage}
              />
            ) : null}
          </section>
        </>
      ) : null}
    </article>
  );
}
