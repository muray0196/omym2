/**
 * Summary: Starts a file, directory, or all-target Refresh planning Operation.
 * Why: Makes metadata re-evaluation explicit and reviewable before execution.
 */
import { useCallback, useContext, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  startRefreshPlan,
  type OperationResultResource,
  type RefreshPlanRequest,
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
import { PageHeader } from "../../ui/primitives/page-header";

export function Component() {
  const bootstrap = useContext(BootstrapContext);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const [targetKind, setTargetKind] =
    useState<RefreshPlanRequest["target_kind"]>("file");
  const [targetPath, setTargetPath] = useState("");
  const libraryId =
    selectedLibraryId ?? bootstrap?.active_library?.library_id ?? "";
  const operationGuard = useAcceptedOperationGuard();
  const mutation = useMutation({
    mutationFn: (body: RefreshPlanRequest) => {
      if (bootstrap === null)
        return Promise.reject(new Error(planningCopy.noBootstrap));
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          startRefreshPlan({
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
      }
    },
    [navigate],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({
      library_id: libraryId,
      target_kind: targetKind,
      target_path: targetKind === "all" ? null : targetPath,
    });
  }

  return (
    <article className={styles.page}>
      <PageHeader
        description={planningCopy.refresh.description}
        eyebrow={planningCopy.refresh.eyebrow}
        title={planningCopy.refresh.title}
      />
      <form className={styles.form} onSubmit={submit}>
        <OperationAvailability bootstrap={bootstrap} />
        <LibrarySelection value={libraryId} onChange={setSelectedLibraryId} />
        <fieldset className={styles.scope} id="refresh-scope" tabIndex={-1}>
          <legend className={styles.legend}>
            {planningCopy.refresh.scopeLabel}
          </legend>
          <div className={styles.scopeOptions}>
            {(["file", "directory", "all"] as const).map((scope) => (
              <label key={scope}>
                <input
                  checked={targetKind === scope}
                  name="refresh-scope"
                  type="radio"
                  value={scope}
                  onChange={() => setTargetKind(scope)}
                />
                {planningCopy.refresh.scopes[scope]}
              </label>
            ))}
          </div>
        </fieldset>
        {targetKind === "all" ? null : (
          <div className={styles.field}>
            <label htmlFor="refresh-target">
              {planningCopy.refresh.pathLabel}
            </label>
            <input
              id="refresh-target"
              required
              type="text"
              value={targetPath}
              onChange={(event) => setTargetPath(event.currentTarget.value)}
            />
            <p className={styles.hint}>{planningCopy.refresh.pathHint}</p>
          </div>
        )}
        <p className={styles.safety}>{planningCopy.noFileMutation}</p>
        <Button
          disabled={
            mutation.isPending ||
            operationGuard.hasActiveOperation ||
            libraryId === "" ||
            bootstrap?.runtime_capabilities.can_start_operations !== true
          }
          type="submit"
          variant="primary"
        >
          {mutation.isPending ? "Starting…" : planningCopy.refresh.submit}
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
  if (result.kind !== "plan_created") return null;
  return (
    <Link className={styles.resultLink} to={`/plans/${result.plan_id}`}>
      {planningCopy.planLink}
    </Link>
  );
}
