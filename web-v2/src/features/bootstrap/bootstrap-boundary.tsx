/**
 * Summary: Presents typed normal, degraded, loading, and disconnected Bootstrap states.
 * Why: Keeps recovery navigation available while backend readiness is incomplete.
 */
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import type {
  ApiError,
  ApiRemediation,
  BootstrapData,
} from "../../api/generated";
import { Icon } from "../../ui/icon";
import { Button } from "../../ui/primitives/button";
import { bootstrapCopy } from "./bootstrap-copy";
import { BootstrapContext } from "./bootstrap-context";
import { BootstrapApiError, bootstrapQuery } from "./bootstrap-query";
import styles from "./bootstrap-boundary.module.css";

export function BootstrapBoundary({ children }: { children: ReactNode }) {
  const query = useQuery(bootstrapQuery);
  const bootstrapData = query.data?.data ?? null;

  return (
    <BootstrapContext value={bootstrapData}>
      {query.isPending ? <LoadingBanner /> : null}
      {query.isError ? (
        query.error instanceof BootstrapApiError ? (
          <UnexpectedBanner
            diagnostics={query.error.envelope.errors}
            onRetry={() => void query.refetch()}
          />
        ) : (
          <DisconnectedBanner onRetry={() => void query.refetch()} />
        )
      ) : null}
      {query.isSuccess ? (
        <BootstrapResult data={query.data.data} errors={query.data.errors} />
      ) : null}
      {children}
    </BootstrapContext>
  );
}

function BootstrapResult({
  data,
  errors,
}: {
  data: BootstrapData | null;
  errors: ApiError[];
}) {
  if (data === null) {
    return <DisconnectedBanner detail={bootstrapCopy.missingRecoveryData} />;
  }

  const diagnostics = uniqueDiagnostics([
    ...errors,
    ...data.config_validation.errors,
    ...data.library_diagnostics,
  ]);
  if (!data.config_validation.valid || diagnostics.length > 0) {
    return <DegradedBanner diagnostics={diagnostics} />;
  }

  return (
    <div
      className={`${styles.banner} ${styles.normal}`}
      data-bootstrap-state="normal"
      role="status"
    >
      <Icon name="check" />
      <div className={styles.content}>
        <p className={styles.summary}>{bootstrapCopy.connected}</p>
        <p
          className={
            data.active_library === null
              ? styles.detail
              : `${styles.detail} ${styles.path}`
          }
        >
          {data.active_library?.root_path ?? bootstrapCopy.noLibrary}
        </p>
      </div>
    </div>
  );
}

function LoadingBanner() {
  return (
    <div
      className={`${styles.banner} ${styles.loading}`}
      data-bootstrap-state="loading"
      role="status"
    >
      <Icon name="info" />
      <p className={styles.summary}>{bootstrapCopy.loading}</p>
    </div>
  );
}

function DegradedBanner({ diagnostics }: { diagnostics: ApiError[] }) {
  return (
    <div
      className={`${styles.banner} ${styles.degraded}`}
      data-bootstrap-state="degraded"
      role="alert"
    >
      <Icon name="warning" />
      <div className={styles.content}>
        <p className={styles.summary}>{bootstrapCopy.degraded}</p>
        <ul
          aria-label={bootstrapCopy.diagnosticsLabel}
          className={styles.diagnostics}
        >
          {diagnostics.map((diagnostic) => (
            <li
              key={`${diagnostic.code}:${diagnostic.field ?? ""}:${diagnostic.message}`}
            >
              {diagnostic.message}
            </li>
          ))}
        </ul>
        <RemediationList diagnostics={diagnostics} />
      </div>
    </div>
  );
}

function UnexpectedBanner({
  diagnostics,
  onRetry,
}: {
  diagnostics: ApiError[];
  onRetry: () => void;
}) {
  const unique = uniqueDiagnostics(diagnostics);
  return (
    <div
      className={`${styles.banner} ${styles.unexpected}`}
      data-bootstrap-state="unexpected"
      role="alert"
    >
      <Icon name="warning" />
      <div className={styles.content}>
        <p className={styles.summary}>{bootstrapCopy.unexpected}</p>
        <ul
          aria-label={bootstrapCopy.diagnosticsLabel}
          className={styles.diagnostics}
        >
          {unique.map((diagnostic) => (
            <li key={`${diagnostic.code}:${diagnostic.field ?? ""}`}>
              {diagnostic.message}
            </li>
          ))}
        </ul>
        <RemediationList diagnostics={unique} />
        {unique.some((diagnostic) => diagnostic.retryable) ? (
          <div className={styles.actions}>
            <Button onClick={onRetry} variant="secondary">
              {bootstrapCopy.retry}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RemediationList({ diagnostics }: { diagnostics: ApiError[] }) {
  const remediations = uniqueRemediations(diagnostics);
  if (remediations.length === 0) {
    return null;
  }

  return (
    <ul
      aria-label={bootstrapCopy.remediationsLabel}
      className={styles.remediations}
    >
      {remediations.map((remediation) => (
        <li
          className={styles.remediation}
          key={`${remediation.label}:${remediation.route ?? ""}:${remediation.command ?? ""}`}
        >
          {remediation.route === undefined ? (
            <span className={styles.remediationLabel}>{remediation.label}</span>
          ) : (
            <Link className={styles.recoveryLink} to={remediation.route}>
              {remediation.label}
            </Link>
          )}
          {remediation.command === undefined ? null : (
            <code className={styles.command}>{remediation.command}</code>
          )}
        </li>
      ))}
    </ul>
  );
}

function DisconnectedBanner({
  detail = bootstrapCopy.disconnectedDetail,
  onRetry,
}: {
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className={`${styles.banner} ${styles.disconnected}`}
      data-bootstrap-state="disconnected"
      role="alert"
    >
      <Icon name="warning" />
      <div className={styles.content}>
        <p className={styles.summary}>{bootstrapCopy.disconnected}</p>
        <p className={styles.detail}>{detail}</p>
        {onRetry === undefined ? null : (
          <div className={styles.actions}>
            <Button onClick={onRetry} variant="secondary">
              {bootstrapCopy.retry}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function uniqueDiagnostics(errors: ApiError[]): ApiError[] {
  return [
    ...new Map(
      errors.map((error) => [
        `${error.code}:${error.field ?? ""}:${error.message}`,
        error,
      ]),
    ).values(),
  ];
}

function uniqueRemediations(errors: ApiError[]): ApiRemediation[] {
  const remediations = errors.flatMap((error) =>
    error.remediation === undefined ? [] : [error.remediation],
  );
  return [
    ...new Map(
      remediations.map((remediation) => [
        `${remediation.label}:${remediation.route ?? ""}:${remediation.command ?? ""}`,
        remediation,
      ]),
    ).values(),
  ];
}
