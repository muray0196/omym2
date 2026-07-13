/**
 * Summary: Starts and monitors backend-authoritative Undo Plan generation for one Run.
 * Why: Routes reversible history through a newly reviewed Plan instead of mutating files directly.
 */
import { useCallback, useContext, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  createUndoPlan,
  type OperationResource,
  type OperationResultResource,
  type RunDetailData,
} from "../../api/generated";
import { Button } from "../../ui/primitives/button";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { ApiDiagnostic } from "../operations/api-diagnostic";
import { useAcceptedOperationGuard } from "../operations/operation-guard";
import { operationRecoveryRoute } from "../operations/operation-routes";
import { OperationMutationError } from "../operations/operation-mutation-error";
import { OperationStatus } from "../operations/operation-status";
import { startOperationSafely } from "../operations/operation-start";
import styles from "../inspection/inspection.module.css";
import { historyCopy } from "./history-copy";

export function UndoPlanControl({ detail }: { detail: RunDetailData }) {
  const bootstrap = useContext(BootstrapContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const controlRef = useRef<HTMLElement>(null);
  const {
    hasActiveOperation,
    recordAcceptedOperation,
    recordTerminalOperation: clearAcceptedOperation,
  } = useAcceptedOperationGuard();
  const refreshHistoryState = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["history"] }),
      queryClient.invalidateQueries({ queryKey: bootstrapQuery.queryKey }),
    ]);
  }, [queryClient]);
  const mutation = useMutation({
    mutationFn: () => {
      if (bootstrap === null) {
        return Promise.reject(new Error(historyCopy.undo.noBootstrap));
      }
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          createUndoPlan({
            baseUrl: globalThis.location.origin,
            headers,
            path: { run_id: detail.run.run_id },
          }),
      });
    },
    onError: refreshHistoryState,
    onSuccess: recordAcceptedOperation,
  });
  const openPlanResult = useCallback(
    (result: OperationResultResource) => {
      if (result.kind === "plan_created") {
        void navigate(`/plans/${result.plan_id}`);
      }
    },
    [navigate],
  );
  const recordTerminalOperation = useCallback(
    (operation: OperationResource) => {
      clearAcceptedOperation();
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      void queryClient.invalidateQueries({ queryKey: bootstrapQuery.queryKey });
      if (operation.status !== "succeeded") {
        controlRef.current?.focus();
      }
    },
    [clearAcceptedOperation, queryClient],
  );
  const diagnostics = detail.capabilities.disabled_reasons.filter(
    (diagnostic) => diagnostic.field === "capabilities.can_create_undo",
  );
  const disabled =
    !detail.capabilities.can_create_undo ||
    detail.active_operation_id !== null ||
    mutation.isPending ||
    hasActiveOperation ||
    bootstrap === null;

  return (
    <section
      aria-labelledby="undo-plan-title"
      className={`${styles.section} ${styles.executionSection}`}
      ref={controlRef}
      tabIndex={-1}
    >
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="undo-plan-title">{historyCopy.undo.title}</h2>
          <p className={styles.subtle}>{historyCopy.undo.description}</p>
        </div>
        {detail.active_operation_id === null ? null : (
          <Link
            className={styles.recoveryLink}
            to={operationRecoveryRoute(detail.active_operation_id)}
          >
            {historyCopy.undo.activeOperation}
          </Link>
        )}
      </div>
      <div className={styles.capabilityPanel}>
        <Button
          aria-describedby={
            diagnostics.length === 0 ? undefined : "undo-capability-reasons"
          }
          disabled={disabled}
          onClick={() => mutation.mutate()}
          variant="primary"
        >
          {mutation.isPending
            ? historyCopy.undo.starting
            : historyCopy.undo.create}
        </Button>
        {diagnostics.length === 0 ? null : (
          <ul className={styles.capabilityReasons} id="undo-capability-reasons">
            {diagnostics.map((diagnostic) => (
              <li
                key={`${diagnostic.code}:${diagnostic.field ?? ""}:${diagnostic.message}`}
              >
                <ApiDiagnostic diagnostic={diagnostic} />
              </li>
            ))}
          </ul>
        )}
      </div>
      {bootstrap === null ? (
        <p className={styles.executionNotice} role="status">
          {historyCopy.undo.noBootstrap}
        </p>
      ) : null}
      {mutation.isError ? (
        <OperationMutationError
          error={mutation.error}
          title={historyCopy.undo.error}
        />
      ) : null}
      {mutation.data && bootstrap ? (
        <OperationStatus
          initialOperation={mutation.data}
          onSucceeded={openPlanResult}
          onTerminal={recordTerminalOperation}
          policy={bootstrap.operation_polling}
          resultAction={undoResultAction}
        />
      ) : null}
    </section>
  );
}

function undoResultAction(result: OperationResultResource) {
  if (result.kind !== "plan_created") return null;
  return (
    <Link className={styles.recoveryLink} to={`/plans/${result.plan_id}`}>
      {historyCopy.undo.planResult}
    </Link>
  );
}
