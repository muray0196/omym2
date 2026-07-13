/**
 * Summary: Presents backend-authoritative Apply, Cancel, and Plan recreation controls.
 * Why: Executes reviewed Plans safely while keeping disabled reasons and durable recovery visible.
 */
import {
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  applyPlan,
  type ApiError,
  type OperationResource,
  type OperationResultResource,
  type PlanDetailData,
  type PlanType,
} from "../../api/generated";
import { Button } from "../../ui/primitives/button";
import { Dialog } from "../../ui/primitives/dialog";
import { LiveRegion } from "../../ui/primitives/live-region";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { ApiDiagnostic } from "../operations/api-diagnostic";
import { useAcceptedOperationGuard } from "../operations/operation-guard";
import { operationRecoveryRoute } from "../operations/operation-routes";
import { OperationMutationError } from "../operations/operation-mutation-error";
import { OperationStatus } from "../operations/operation-status";
import { startOperationSafely } from "../operations/operation-start";
import { planCopy } from "./plan-copy";
import { cancelPlanSafely } from "./plan-execution";
import styles from "./plan-inspection.module.css";

const RECREATE_ROUTES: Partial<Record<PlanType, string>> = {
  add: "/plans/new/add",
  organize: "/plans/new/organize",
  refresh: "/plans/new/refresh",
};

export function PlanExecutionControls({ detail }: { detail: PlanDetailData }) {
  const bootstrap = useContext(BootstrapContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const cancelDismissRef = useRef<HTMLButtonElement>(null);
  const cancelReturnFocusRef = useRef<HTMLElement | null>(null);
  const controlsRef = useRef<HTMLElement>(null);
  const [announcement, setAnnouncement] = useState("");
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const {
    hasActiveOperation,
    recordAcceptedOperation,
    recordTerminalOperation: clearAcceptedOperation,
  } = useAcceptedOperationGuard();
  const { capabilities, plan } = detail;
  const recreateRoute = RECREATE_ROUTES[plan.plan_type];

  const refreshPlanState = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plans"] }),
      queryClient.invalidateQueries({ queryKey: bootstrapQuery.queryKey }),
    ]);
  }, [queryClient]);

  const applyMutation = useMutation({
    mutationFn: () => {
      if (bootstrap === null) {
        return Promise.reject(new Error(planCopy.execution.noBootstrap));
      }
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          applyPlan({
            baseUrl: globalThis.location.origin,
            headers,
            path: { plan_id: plan.plan_id },
          }),
      });
    },
    onError: refreshPlanState,
    onSuccess: recordAcceptedOperation,
  });
  const cancelMutation = useMutation({
    mutationFn: () => {
      if (bootstrap === null) {
        return Promise.reject(new Error(planCopy.execution.noBootstrap));
      }
      return cancelPlanSafely({
        csrfToken: bootstrap.csrf_token,
        planId: plan.plan_id,
        queryClient,
      });
    },
    onMutate: () => setAnnouncement(""),
    onError: refreshPlanState,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
      setAnnouncement(planCopy.execution.cancelledAnnouncement);
      controlsRef.current?.focus();
    },
  });
  const openRunResult = useCallback(
    (result: OperationResultResource) => {
      if (result.kind === "run_completed") {
        void navigate(`/history/${result.run_id}`);
      }
    },
    [navigate],
  );
  const recordTerminalOperation = useCallback(
    (operation: OperationResource) => {
      clearAcceptedOperation();
      void refreshPlanState();
      if (operation.status !== "succeeded") {
        controlsRef.current?.focus();
      }
    },
    [clearAcceptedOperation, refreshPlanState],
  );

  const locallyBusy =
    applyMutation.isPending || cancelMutation.isPending || hasActiveOperation;
  const applyDisabled =
    !capabilities.can_apply || locallyBusy || bootstrap === null;
  const cancelDisabled =
    !capabilities.can_cancel || locallyBusy || bootstrap === null;
  const recreateDisabled =
    !capabilities.can_recreate || locallyBusy || recreateRoute === undefined;

  return (
    <section
      aria-labelledby="plan-execution-title"
      className={styles.executionSection}
      ref={controlsRef}
      tabIndex={-1}
    >
      <LiveRegion>{announcement}</LiveRegion>
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="plan-execution-title">{planCopy.execution.title}</h2>
          <p className={styles.subtle}>{planCopy.execution.description}</p>
        </div>
        {detail.active_operation_id === null ? null : (
          <Link
            className={styles.recoveryLink}
            to={operationRecoveryRoute(detail.active_operation_id)}
          >
            {planCopy.execution.activeOperation}
          </Link>
        )}
      </div>

      <ExecutionImpact detail={detail} />

      <div className={styles.executionControls}>
        <CapabilityControl
          control={
            <Button
              aria-describedby={reasonId("can_apply", capabilities)}
              disabled={applyDisabled}
              onClick={() => applyMutation.mutate()}
              variant="primary"
            >
              {applyMutation.isPending
                ? planCopy.execution.startingApply
                : planCopy.execution.apply}
            </Button>
          }
          diagnostics={capabilityReasons(
            capabilities.disabled_reasons,
            "can_apply",
          )}
          id="can_apply"
        />
        <CapabilityControl
          control={
            <Button
              aria-describedby={reasonId("can_cancel", capabilities)}
              disabled={cancelDisabled}
              onClick={() => {
                cancelReturnFocusRef.current = cancelButtonRef.current;
                setCancelDialogOpen(true);
              }}
              ref={cancelButtonRef}
              variant="secondary"
            >
              {cancelMutation.isPending
                ? planCopy.execution.cancelling
                : planCopy.execution.cancel}
            </Button>
          }
          diagnostics={capabilityReasons(
            capabilities.disabled_reasons,
            "can_cancel",
          )}
          id="can_cancel"
        />
        <CapabilityControl
          control={
            <Button
              aria-describedby={reasonId("can_recreate", capabilities)}
              disabled={recreateDisabled}
              onClick={() => {
                if (recreateRoute !== undefined) void navigate(recreateRoute);
              }}
              variant="quiet"
            >
              {planCopy.execution.recreate}
            </Button>
          }
          diagnostics={capabilityReasons(
            capabilities.disabled_reasons,
            "can_recreate",
          )}
          id="can_recreate"
        />
      </div>

      {bootstrap === null ? (
        <p className={styles.executionNotice} role="status">
          {planCopy.execution.noBootstrap}
        </p>
      ) : null}
      {applyMutation.isError ? (
        <OperationMutationError
          error={applyMutation.error}
          title={planCopy.execution.applyError}
        />
      ) : null}
      {cancelMutation.isError ? (
        <OperationMutationError
          error={cancelMutation.error}
          title={planCopy.execution.cancelError}
        />
      ) : null}
      {applyMutation.data && bootstrap ? (
        <OperationStatus
          initialOperation={applyMutation.data}
          onSucceeded={openRunResult}
          onTerminal={recordTerminalOperation}
          policy={bootstrap.operation_polling}
          resultAction={applyResultAction}
        />
      ) : null}
      <Dialog
        closeLabel={planCopy.execution.cancelDialogClose}
        initialFocusRef={cancelDismissRef}
        label={planCopy.execution.cancelDialogTitle}
        onRequestClose={() => setCancelDialogOpen(false)}
        open={cancelDialogOpen}
        returnFocusRef={cancelReturnFocusRef}
      >
        <p>{planCopy.execution.cancelDialogBody}</p>
        <div className={styles.executionControls}>
          <Button
            onClick={() => setCancelDialogOpen(false)}
            ref={cancelDismissRef}
            variant="quiet"
          >
            {planCopy.execution.cancelDialogDismiss}
          </Button>
          <Button
            onClick={() => {
              cancelReturnFocusRef.current = controlsRef.current;
              setCancelDialogOpen(false);
              cancelMutation.mutate();
            }}
            variant="secondary"
          >
            {planCopy.execution.cancelDialogConfirm}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}

function ExecutionImpact({ detail }: { detail: PlanDetailData }) {
  const blocked = countActions(detail.summary.counts.blocked);
  const executable = countActions(detail.summary.counts.planned);
  if (blocked === 0) return null;
  return (
    <p className={styles.executionNotice}>
      {executable === 0
        ? planCopy.execution.blockedOnly
        : planCopy.execution.mixedBlocked(blocked)}
    </p>
  );
}

function countActions(counts: PlanDetailData["summary"]["counts"]["planned"]) {
  return counts.move + counts.refresh_metadata + counts.skip;
}

function CapabilityControl({
  control,
  diagnostics,
  id,
}: {
  control: ReactNode;
  diagnostics: ApiError[];
  id: string;
}) {
  return (
    <div className={styles.capabilityControl}>
      {control}
      {diagnostics.length === 0 ? null : (
        <ul className={styles.capabilityReasons} id={`plan-${id}-reasons`}>
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
  );
}

function capabilityReasons(diagnostics: ApiError[], capability: string) {
  return diagnostics.filter(
    (diagnostic) => diagnostic.field === `capabilities.${capability}`,
  );
}

function reasonId(
  capability: string,
  capabilities: PlanDetailData["capabilities"],
) {
  return capabilityReasons(capabilities.disabled_reasons, capability).length ===
    0
    ? undefined
    : `plan-${capability}-reasons`;
}

function applyResultAction(result: OperationResultResource) {
  if (result.kind !== "run_completed") return null;
  return (
    <Link className={styles.recoveryLink} to={`/history/${result.run_id}`}>
      {planCopy.execution.historyResult}
    </Link>
  );
}
