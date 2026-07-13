/**
 * Summary: Starts an Add planning Operation from backend-owned Library input.
 * Why: Creates reviewable import evidence without mutating Library music files.
 */
import { useCallback, useContext, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  startAddPlan,
  type AddPlanRequest,
  type OperationResultResource,
} from "../../api/generated";
import { BootstrapContext } from "../../features/bootstrap/bootstrap-context";
import { OperationStatus } from "../../features/operations/operation-status";
import { useAcceptedOperationGuard } from "../../features/operations/operation-guard";
import { startOperationSafely } from "../../features/operations/operation-start";
import { LibrarySelection } from "../../features/planning/library-selection";
import { OperationAvailability } from "../../features/planning/operation-availability";
import { planningCopy } from "../../features/planning/planning-copy";
import { PlanningMutationError } from "../../features/planning/planning-errors";
import styles from "../../features/planning/planning.module.css";
import { Button } from "../../ui/primitives/button";
import { RouteHeading } from "../../ui/primitives/route-heading";

export function Component() {
  const bootstrap = useContext(BootstrapContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [sourcePath, setSourcePath] = useState("");
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const libraryId =
    selectedLibraryId ?? bootstrap?.active_library?.library_id ?? "";
  const operationGuard = useAcceptedOperationGuard();
  const mutation = useMutation({
    mutationFn: (body: AddPlanRequest) => {
      if (bootstrap === null)
        return Promise.reject(new Error(planningCopy.noBootstrap));
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          startAddPlan({
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
    mutation.mutate({
      library_id: libraryId || null,
      source_path: sourcePath.trim() || null,
    });
  }

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{planningCopy.add.eyebrow}</p>
        <RouteHeading>{planningCopy.add.title}</RouteHeading>
        <p className={styles.description}>{planningCopy.add.description}</p>
      </header>
      <form className={styles.form} onSubmit={submit}>
        <OperationAvailability bootstrap={bootstrap} />
        <LibrarySelection value={libraryId} onChange={setSelectedLibraryId} />
        <div className={styles.field}>
          <label htmlFor="add-source">{planningCopy.add.sourceLabel}</label>
          <input
            id="add-source"
            type="text"
            value={sourcePath}
            onChange={(event) => setSourcePath(event.currentTarget.value)}
          />
          <p className={styles.hint}>{planningCopy.add.sourceHint}</p>
        </div>
        <p className={styles.safety}>{planningCopy.noFileMutation}</p>
        <Button
          disabled={
            mutation.isPending ||
            operationGuard.hasActiveOperation ||
            bootstrap?.runtime_capabilities.can_start_operations !== true
          }
          type="submit"
          variant="primary"
        >
          {mutation.isPending ? "Starting…" : planningCopy.add.submit}
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
