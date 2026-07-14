/**
 * Summary: Recovers and polls one durable Operation from its addressable browser URL.
 * Why: Keeps accepted work inspectable after reload, navigation, or a lost mutation response.
 */
import { useCallback, useContext } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import type { OperationResultResource } from "../../api/generated";
import { BootstrapContext } from "../../features/bootstrap/bootstrap-context";
import { bootstrapQuery } from "../../features/bootstrap/bootstrap-query";
import { operationCopy } from "../../features/operations/operation-copy";
import { operationRecoveryQuery } from "../../features/operations/operation-polling";
import { OperationApiError } from "../../features/operations/operation-start";
import { OperationStatus } from "../../features/operations/operation-status";
import styles from "../../features/operations/operation.module.css";
import { Button } from "../../ui/primitives/button";
import { PageHeader } from "../../ui/primitives/page-header";

export function Component() {
  const { operationId = "" } = useParams();
  const bootstrap = useContext(BootstrapContext);
  const queryClient = useQueryClient();
  const query = useQuery(operationRecoveryQuery(operationId));
  const refreshBootstrap = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: bootstrapQuery.queryKey });
  }, [queryClient]);

  return (
    <article className={styles.page}>
      <PageHeader
        description={operationCopy.recoveryDescription}
        eyebrow={operationCopy.recoveryEyebrow}
        title={operationCopy.recoveryTitle}
      />
      {query.isPending ? <p role="status">{operationCopy.loading}</p> : null}
      {query.isError ? (
        <OperationRecoveryError
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {query.data && bootstrap ? (
        <RecoveredOperationStatus
          initialOperation={query.data}
          onTerminal={refreshBootstrap}
          policy={bootstrap.operation_polling}
        />
      ) : null}
      {query.data && bootstrap === null ? (
        <p className={styles.warning} role="alert">
          {operationCopy.pollingUnavailable}
        </p>
      ) : null}
    </article>
  );
}

function RecoveredOperationStatus({
  initialOperation,
  onTerminal,
  policy,
}: {
  initialOperation: Parameters<typeof OperationStatus>[0]["initialOperation"];
  onTerminal: () => void;
  policy: Parameters<typeof OperationStatus>[0]["policy"];
}) {
  return (
    <OperationStatus
      initialOperation={initialOperation}
      onTerminal={onTerminal}
      policy={policy}
      resultAction={operationResultAction}
    />
  );
}

function OperationRecoveryError({
  error,
  onRetry,
}: {
  error: Error;
  onRetry: () => void;
}) {
  const title =
    error instanceof OperationApiError && error.status === 410
      ? operationCopy.expiredTitle
      : error instanceof OperationApiError && error.status === 404
        ? operationCopy.notFoundTitle
        : operationCopy.readErrorTitle;
  const diagnostics =
    error instanceof OperationApiError
      ? error.envelope.errors.map((diagnostic) => diagnostic.message)
      : [error.message];
  const canRetry =
    !(error instanceof OperationApiError) ||
    error.envelope.errors.some((diagnostic) => diagnostic.retryable);
  return (
    <section className={styles.error} role="alert">
      <h2>{title}</h2>
      <ul>
        {diagnostics.map((diagnostic) => (
          <li key={diagnostic}>{diagnostic}</li>
        ))}
      </ul>
      {canRetry ? (
        <Button onClick={onRetry}>{operationCopy.retryRead}</Button>
      ) : null}
    </section>
  );
}

function operationResultAction(result: OperationResultResource) {
  if (result.kind === "plan_created") {
    return (
      <Link to={`/plans/${result.plan_id}`}>{operationCopy.inspectPlan}</Link>
    );
  }
  if (result.kind === "registered_without_plan") {
    return <Link to="/library">{operationCopy.inspectLibrary}</Link>;
  }
  if (result.kind === "run_completed") {
    return (
      <Link to={`/history/${result.run_id}`}>{operationCopy.inspectRun}</Link>
    );
  }
  if (result.kind === "check_completed") {
    return <Link to="/health">{operationCopy.inspectHealth}</Link>;
  }
  return null;
}
