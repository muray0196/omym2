/**
 * Summary: Presents durable Operation progress, connectivity, and typed results.
 * Why: Gives planning and Check routes one accessible asynchronous status surface.
 */
import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  OperationPollingPolicy,
  OperationRef,
  OperationResource,
  OperationResultResource,
} from "../../api/generated";
import { LiveRegion } from "../../ui/primitives/live-region";
import { ApiDiagnostic } from "./api-diagnostic";
import { operationCopy } from "./operation-copy";
import {
  operationPollingErrors,
  useOperationPolling,
} from "./operation-polling";
import { OperationApiError } from "./operation-start";
import styles from "./operation.module.css";

export function OperationStatus({
  initialOperation,
  onSucceeded,
  onTerminal,
  policy,
  resultAction,
}: {
  initialOperation: OperationRef | OperationResource;
  onSucceeded?: (result: OperationResultResource) => void;
  onTerminal?: (operation: OperationResource) => void;
  policy: OperationPollingPolicy;
  resultAction: (result: OperationResultResource) => ReactNode;
}) {
  const polling = useOperationPolling({ initialOperation, policy });
  const operation =
    polling.data ??
    ("progress" in initialOperation ? initialOperation : undefined);
  const status = operation?.status ?? initialOperation.status;
  const terminalError = operation?.error;
  const queryErrors = operationPollingErrors(polling.error);
  const expired =
    polling.error instanceof OperationApiError && polling.error.status === 410;
  const announcement = announcementFor(operation, polling.connectivity);

  useEffect(() => {
    if (operation === undefined || !isTerminalStatus(operation.status)) {
      return;
    }
    onTerminal?.(operation);
    if (operation.status === "succeeded" && operation.result !== null) {
      onSucceeded?.(operation.result);
    }
  }, [onSucceeded, onTerminal, operation]);

  return (
    <section
      className={styles.panel}
      aria-labelledby="operation-progress-title"
    >
      <LiveRegion>{announcement}</LiveRegion>
      <div className={styles.heading}>
        <h2 id="operation-progress-title">{operationCopy.progress}</h2>
        <span className={styles.status}>{statusLabel(status)}</span>
      </div>
      <p className={styles.operationId}>{initialOperation.operation_id}</p>
      {polling.connectivity === "disconnected" ? (
        <p className={styles.warning} role="status">
          {operationCopy.disconnected}
        </p>
      ) : null}
      {status === "queued" || status === "running" ? (
        <OperationStage stageCode={operation?.progress.stage_code ?? null} />
      ) : null}
      {operation?.progress.completed_units !== null &&
      operation?.progress.completed_units !== undefined &&
      operation.progress.total_units !== null ? (
        <p>
          {operationCopy.units(
            operation.progress.completed_units,
            operation.progress.total_units,
          )}
        </p>
      ) : null}
      {operation?.progress.message ? <p>{operation.progress.message}</p> : null}
      {terminalError ? (
        <div className={styles.error} role="alert">
          <strong>{statusLabel(status)}</strong>
          <ApiDiagnostic diagnostic={terminalError} />
        </div>
      ) : null}
      {expired ? (
        <p className={styles.error} role="alert">
          {operationCopy.expired}
        </p>
      ) : null}
      {!expired && queryErrors.length > 0 ? (
        <ul
          className={styles.errors}
          aria-label="Operation errors"
          role="alert"
        >
          {queryErrors.map((error) => (
            <li key={`${error.code}:${error.field ?? ""}:${error.message}`}>
              <ApiDiagnostic diagnostic={error} />
            </li>
          ))}
        </ul>
      ) : null}
      {polling.isError &&
      polling.connectivity === "connected" &&
      queryErrors.length === 0 ? (
        <p className={styles.error} role="alert">
          {operationCopy.unexpected}
        </p>
      ) : null}
      {operation?.status === "succeeded" && operation.result !== null ? (
        <div className={styles.result}>{resultAction(operation.result)}</div>
      ) : null}
      {operation !== undefined &&
      (operation.status === "failed" || operation.status === "interrupted") ? (
        <OperationAssociations operation={operation} />
      ) : null}
    </section>
  );
}

function OperationStage({ stageCode }: { stageCode: string | null }) {
  if (stageCode === null) {
    return <p>{operationCopy.unknownStage}</p>;
  }
  return (
    <p>
      {operationCopy.unknownStage}: {operationCopy.stageCode}{" "}
      <code className={styles.stageCode}>{stageCode}</code>
    </p>
  );
}

function OperationAssociations({
  operation,
}: {
  operation: OperationResource;
}) {
  const associations = [
    operation.plan_id === null
      ? null
      : { label: operationCopy.inspectPlan, to: `/plans/${operation.plan_id}` },
    operation.run_id === null
      ? null
      : { label: operationCopy.inspectRun, to: `/history/${operation.run_id}` },
    operation.library_id === null
      ? null
      : { label: operationCopy.inspectLibrary, to: "/library" },
  ].filter((association) => association !== null);

  if (associations.length === 0) {
    return null;
  }
  return (
    <nav aria-label={operationCopy.associations}>
      <ul className={styles.associations}>
        {associations.map((association) => (
          <li key={association.to}>
            <Link to={association.to}>{association.label}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function isTerminalStatus(status: OperationResource["status"]) {
  return (
    status === "succeeded" || status === "failed" || status === "interrupted"
  );
}

function statusLabel(status: OperationRef["status"]) {
  return operationCopy[status];
}

function announcementFor(
  operation: OperationResource | undefined,
  connectivity: "connected" | "disconnected",
) {
  if (connectivity === "disconnected") return operationCopy.disconnected;
  if (operation === undefined) return operationCopy.accepted;
  if (operation.status === "succeeded") {
    if (operation.result?.kind === "plan_created")
      return operationCopy.planCreated;
    if (operation.result?.kind === "registered_without_plan")
      return operationCopy.registered(operation.result.track_count);
    if (operation.result?.kind === "check_completed")
      return operationCopy.checkCompleted(operation.result.issue_count);
    if (operation.result?.kind === "run_completed")
      return operationCopy.runCompleted;
    return operationCopy.succeeded;
  }
  if (operation.status === "failed" || operation.status === "interrupted")
    return operation.error?.message ?? statusLabel(operation.status);
  return operation.progress.message ?? statusLabel(operation.status);
}
