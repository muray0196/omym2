/**
 * Summary: Renders the read-only operating overview from typed persisted snapshots.
 * Why: Gives users one readiness, Plan, History, and Health starting point before mutations ship.
 */
import { useContext, type ContextType } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  getCheckIssues,
  getHistory,
  listPlans,
  type CheckIssuesData,
  type PaginatedDataPlanSummary,
  type PaginatedDataRunHeader,
} from "../../api/generated";
import { BootstrapContext } from "../../features/bootstrap/bootstrap-context";
import { runStatusLabel } from "../../features/history/history-catalog";
import { LibraryStatusBadge } from "../../features/library/library-presentation";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { routeCopy } from "../route-copy";
import styles from "../route.module.css";

export function Component() {
  const bootstrap = useContext(BootstrapContext);
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: ({ signal }) => loadOverview(signal),
  });

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{routeCopy.overview.eyebrow}</p>
        <RouteHeading>{routeCopy.overview.title}</RouteHeading>
        <p className={styles.description}>{routeCopy.overview.description}</p>
      </header>
      <div className={styles.cards}>
        <ReadinessCard bootstrap={bootstrap} />
        <SnapshotCard
          body={planSummary(overview.data?.plans)}
          href="/plans"
          linkLabel={routeCopy.overview.openPlans}
          loading={overview.isPending}
          title={routeCopy.overview.plansTitle}
        />
        <SnapshotCard
          body={historySummary(overview.data?.history)}
          href="/history"
          linkLabel={routeCopy.overview.openHistory}
          loading={overview.isPending}
          title={routeCopy.overview.historyTitle}
        />
        <SnapshotCard
          body={healthSummary(overview.data?.health)}
          href="/health"
          linkLabel={routeCopy.overview.openHealth}
          loading={overview.isPending}
          title={routeCopy.overview.healthTitle}
        />
      </div>
      {overview.isError ? (
        <section
          className={`${styles.placeholder} ${styles.error}`}
          role="alert"
        >
          <h2>{routeCopy.overview.errorTitle}</h2>
          <p>{routeCopy.overview.errorBody}</p>
          <button
            className={styles.retryButton}
            onClick={() => void overview.refetch()}
            type="button"
          >
            {routeCopy.overview.retry}
          </button>
        </section>
      ) : null}
    </article>
  );
}

function ReadinessCard({
  bootstrap,
}: {
  bootstrap: ContextType<typeof BootstrapContext>;
}) {
  const library = bootstrap?.active_library;
  return (
    <section className={styles.card}>
      <h2>{routeCopy.overview.readinessTitle}</h2>
      <p className={styles.cardValue}>
        {library === undefined || bootstrap === null ? (
          routeCopy.overview.loading
        ) : library === null ? (
          routeCopy.overview.noLibrary
        ) : (
          <LibraryStatusBadge value={library.status} />
        )}
      </p>
      <p className={styles.path}>
        {library?.root_path ?? routeCopy.overview.readinessBody}
      </p>
    </section>
  );
}

function SnapshotCard({
  body,
  href,
  linkLabel,
  loading,
  title,
}: {
  body: string;
  href: string;
  linkLabel: string;
  loading: boolean;
  title: string;
}) {
  return (
    <section className={styles.card}>
      <h2>{title}</h2>
      <p>{loading ? routeCopy.overview.loading : body}</p>
      <Link className={styles.cardLink} data-list-item to={href}>
        {linkLabel}
      </Link>
    </section>
  );
}

async function loadOverview(signal: AbortSignal) {
  const [plansResponse, historyResponse, healthResponse] = await Promise.all([
    listPlans({
      baseUrl: globalThis.location.origin,
      query: { limit: 3, status: "ready" },
      signal,
    }),
    getHistory({
      baseUrl: globalThis.location.origin,
      query: { limit: 1 },
      signal,
    }),
    getCheckIssues({
      baseUrl: globalThis.location.origin,
      query: { limit: 3 },
      signal,
    }),
  ]);
  return {
    plans: unwrap(plansResponse, routeCopy.overview.plansError),
    history: unwrap(historyResponse, routeCopy.overview.historyError),
    health: unwrap(healthResponse, routeCopy.overview.healthError),
  };
}

function unwrap<T>(
  response: { data?: { data: T | null }; error?: unknown },
  message: string,
): T {
  if (response.error !== undefined || response.data?.data == null) {
    throw new Error(message);
  }
  return response.data.data;
}

function planSummary(data: PaginatedDataPlanSummary | undefined) {
  if (data === undefined || data.page.total === 0) {
    return routeCopy.overview.noReadyPlans;
  }
  return `${String(data.page.total)} ${routeCopy.overview.readyPlans}`;
}

function historySummary(data: PaginatedDataRunHeader | undefined) {
  const run = data?.items[0];
  return run === undefined
    ? routeCopy.overview.noRuns
    : `${runStatusLabel(run.status)} · ${new Date(run.started_at).toLocaleString()}`;
}

function healthSummary(data: CheckIssuesData | undefined) {
  if (data === undefined || data.page.total === 0) {
    return routeCopy.overview.noHealthIssues;
  }
  return `${String(data.page.total)} ${routeCopy.overview.healthIssues}`;
}
