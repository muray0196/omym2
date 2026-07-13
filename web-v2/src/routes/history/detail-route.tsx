/**
 * Summary: Renders one Run with capabilities and durable FileEvent evidence.
 * Why: Surfaces partial, failed, and unknown mutation outcomes without offering Undo.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  eventTypeLabel,
  formatTimestamp,
} from "../../features/history/history-catalog";
import { historyCopy } from "../../features/history/history-copy";
import {
  EventStatusBadge,
  RunStatusBadge,
} from "../../features/history/history-presentation";
import {
  runDetailQuery,
  runEventFacetsQuery,
  runEventGroupsInfiniteQuery,
  runEventsInfiniteQuery,
} from "../../features/history/history-query";
import {
  eventStatusOptions,
  useEventFilters,
} from "../../features/history/history-url-state";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import styles from "../../features/inspection/inspection.module.css";
import { InspectionApiError } from "../../features/inspection/query-errors";
import { Button } from "../../ui/primitives/button";
import { RouteHeading } from "../../ui/primitives/route-heading";

export function Component() {
  const { runId = "" } = useParams();
  const { filters, updateFilters } = useEventFilters();
  const detailQuery = useQuery(runDetailQuery(runId));
  const eventsQuery = useInfiniteQuery(runEventsInfiniteQuery(runId, filters));
  const facetsQuery = useQuery(runEventFacetsQuery(runId));
  const groupsQuery = useInfiniteQuery(runEventGroupsInfiniteQuery(runId));

  if (detailQuery.isPending)
    return (
      <section className={styles.state} role="status">
        {historyCopy.detail.loading}
      </section>
    );
  if (detailQuery.isError) {
    if (
      detailQuery.error instanceof InspectionApiError &&
      detailQuery.error.envelope.errors.some(
        (error) => error.code === "run_not_found",
      )
    ) {
      return (
        <article className={styles.page}>
          <RouteHeading>{historyCopy.detail.title}</RouteHeading>
          <section className={styles.state}>
            <p>{historyCopy.detail.notFound}</p>
            <Link className={styles.backLink} to="/history">
              {historyCopy.detail.back}
            </Link>
          </section>
        </article>
      );
    }
    return (
      <InspectionErrorState
        error={detailQuery.error}
        onRetry={() => void detailQuery.refetch()}
        title={historyCopy.detail.error}
      />
    );
  }

  const detail = detailQuery.data;
  const events = eventsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const groups = groupsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const run = detail.run;

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.backLink} to="/history">
          {historyCopy.detail.back}
        </Link>
        <p className={styles.eyebrow}>{historyCopy.detail.eyebrow}</p>
        <RouteHeading>{historyCopy.detail.title}</RouteHeading>
        <span className={styles.id}>{run.run_id}</span>
      </header>
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
          {detail.active_operation_id ? (
            <div>
              <dt>{historyCopy.labels.activeOperation}</dt>
              <dd className={styles.id}>{detail.active_operation_id}</dd>
            </div>
          ) : null}
        </dl>
        {run.error_summary ? (
          <div className={styles.warning}>
            <strong>{historyCopy.labels.error}</strong>
            <p>{run.error_summary}</p>
          </div>
        ) : null}
      </section>
      <section className={styles.section}>
        <h2>{historyCopy.detail.capability}</h2>
        {detail.capabilities.can_create_undo ? (
          <p>{historyCopy.detail.eligible}</p>
        ) : (
          <ul className={styles.diagnostics}>
            {detail.capabilities.disabled_reasons.map((reason) => (
              <li key={`${reason.code}:${reason.message}`}>
                {reason.message}
                {reason.remediation?.route ? (
                  <>
                    {" "}
                    <Link to={reason.remediation.route}>
                      {reason.remediation.label}
                    </Link>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className={styles.filters} aria-label="FileEvent filters">
        <label className={styles.field}>
          Event status
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
            <option value="">All event statuses</option>
            {eventStatusOptions.map((status) => (
              <option key={status} value={status}>
                {status}
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
                <span className={styles.count}>{facet.count}</span>
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
                  <span className={styles.count}>{group.count}</span>
                </li>
              ))}
            </ul>
          )}
          {groupsQuery.hasNextPage ? (
            <Button
              onClick={() => void groupsQuery.fetchNextPage()}
              disabled={groupsQuery.isFetchingNextPage}
            >
              {historyCopy.detail.loadMoreGroups}
            </Button>
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
                  {eventTypeLabel(event.event_type)} · sequence{" "}
                  {event.sequence_no}
                </p>
                <dl className={styles.metadataList}>
                  <div>
                    <dt>{historyCopy.labels.actionId}</dt>
                    <dd className={styles.id}>{event.plan_action_id}</dd>
                  </div>
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
        {eventsQuery.hasNextPage ? (
          <Button
            onClick={() => void eventsQuery.fetchNextPage()}
            disabled={eventsQuery.isFetchingNextPage}
          >
            {historyCopy.detail.loadMoreEvents}
          </Button>
        ) : null}
      </section>
    </article>
  );
}
