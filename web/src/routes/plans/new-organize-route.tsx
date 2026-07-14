/**
 * Summary: Starts Library registration or reconciliation as an Organize Operation.
 * Why: Makes the explicit Library-root workflow reviewable before any file mutation.
 */
import { useCallback, useContext, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  startOrganizePlan,
  type OperationResultResource,
  type OrganizePlanRequest,
} from "../../api/generated";
import { BootstrapContext } from "../../features/bootstrap/bootstrap-context";
import { OperationStatus } from "../../features/operations/operation-status";
import { useAcceptedOperationGuard } from "../../features/operations/operation-guard";
import { startOperationSafely } from "../../features/operations/operation-start";
import { OperationAvailability } from "../../features/planning/operation-availability";
import { planningCopy } from "../../features/planning/planning-copy";
import { PlanningMutationError } from "../../features/planning/planning-errors";
import styles from "../../features/planning/planning.module.css";
import { Button } from "../../ui/primitives/button";
import { PageHeader } from "../../ui/primitives/page-header";

export function Component() {
  const bootstrap = useContext(BootstrapContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [libraryRoot, setLibraryRoot] = useState("");
  const operationGuard = useAcceptedOperationGuard();
  const mutation = useMutation({
    mutationFn: (body: OrganizePlanRequest) => {
      if (bootstrap === null)
        return Promise.reject(new Error(planningCopy.noBootstrap));
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          startOrganizePlan({
            baseUrl: globalThis.location.origin,
            body,
            headers,
          }),
      });
    },
    onSuccess: operationGuard.recordAcceptedOperation,
  });
  const openTerminalResult = useCallback(
    (result: OperationResultResource) => {
      if (result.kind === "plan_created") {
        void navigate(`/plans/${result.plan_id}`);
      } else if (result.kind === "registered_without_plan") {
        void navigate("/library");
      }
    },
    [navigate],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ library_root: libraryRoot });
  }

  return (
    <article className={styles.page}>
      <PageHeader
        description={planningCopy.organize.description}
        eyebrow={planningCopy.organize.eyebrow}
        title={planningCopy.organize.title}
      />
      <form className={styles.form} onSubmit={submit}>
        <OperationAvailability
          bootstrap={bootstrap}
          capability="can_start_organize"
        />
        <div className={styles.field}>
          <label htmlFor="organize-root">
            {planningCopy.organize.rootLabel}
          </label>
          <input
            id="organize-root"
            required
            type="text"
            value={libraryRoot}
            onChange={(event) => setLibraryRoot(event.currentTarget.value)}
          />
          <p className={styles.hint}>{planningCopy.organize.rootHint}</p>
        </div>
        <p className={styles.safety}>{planningCopy.noFileMutation}</p>
        <Button
          disabled={
            mutation.isPending ||
            operationGuard.hasActiveOperation ||
            bootstrap?.runtime_capabilities.can_start_organize !== true
          }
          type="submit"
          variant="primary"
        >
          {mutation.isPending ? "Starting…" : planningCopy.organize.submit}
        </Button>
        {mutation.isError ? (
          <PlanningMutationError error={mutation.error} />
        ) : null}
      </form>
      {mutation.data && bootstrap ? (
        <OperationStatus
          initialOperation={mutation.data}
          onSucceeded={openTerminalResult}
          onTerminal={operationGuard.recordTerminalOperation}
          policy={bootstrap.operation_polling}
          resultAction={planningResultAction}
        />
      ) : null}
    </article>
  );
}

function planningResultAction(result: OperationResultResource) {
  if (result.kind === "plan_created") {
    return (
      <Link className={styles.resultLink} to={`/plans/${result.plan_id}`}>
        {planningCopy.planLink}
      </Link>
    );
  }
  if (result.kind === "registered_without_plan") {
    return (
      <>
        <span>Registered {result.track_count} tracks.</span>
        <Link className={styles.resultLink} to="/library">
          {planningCopy.libraryLink}
        </Link>
      </>
    );
  }
  return null;
}
