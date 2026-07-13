/**
 * Summary: Starts and monitors an exclusive persisted Check Operation.
 * Why: Recomputes Health evidence without mutating Library files or managed Tracks.
 */
import { useCallback, useContext, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  startCheck,
  type CheckRunRequest,
  type OperationResultResource,
} from "../../api/generated";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { OperationStatus } from "../operations/operation-status";
import { useAcceptedOperationGuard } from "../operations/operation-guard";
import { startOperationSafely } from "../operations/operation-start";
import { LibrarySelection } from "../planning/library-selection";
import { OperationAvailability } from "../planning/operation-availability";
import { PlanningMutationError } from "../planning/planning-errors";
import planningStyles from "../planning/planning.module.css";
import { Button } from "../../ui/primitives/button";
import { healthCopy } from "./health-copy";

export function CheckRunControl() {
  const bootstrap = useContext(BootstrapContext);
  const queryClient = useQueryClient();
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(
    null,
  );
  const libraryId =
    selectedLibraryId ?? bootstrap?.active_library?.library_id ?? "";
  const operationGuard = useAcceptedOperationGuard();
  const mutation = useMutation({
    mutationFn: (body: CheckRunRequest) => {
      if (bootstrap === null)
        return Promise.reject(new Error("Startup state is unavailable."));
      return startOperationSafely({
        csrfToken: bootstrap.csrf_token,
        queryClient,
        send: (headers) =>
          startCheck({
            baseUrl: globalThis.location.origin,
            body,
            headers,
          }),
      });
    },
    onSuccess: operationGuard.recordAcceptedOperation,
  });
  const refreshFindings = useCallback(
    (result: OperationResultResource) => {
      if (result.kind === "check_completed") {
        void queryClient.invalidateQueries({ queryKey: ["check"] });
      }
    },
    [queryClient],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ library_id: libraryId || null });
  }

  return (
    <section aria-labelledby="run-check-heading">
      <form className={planningStyles.form} onSubmit={submit}>
        <h2 id="run-check-heading">{healthCopy.run.title}</h2>
        <p>{healthCopy.run.description}</p>
        <OperationAvailability bootstrap={bootstrap} />
        <LibrarySelection
          allowEmpty
          label={healthCopy.run.libraryLabel}
          value={libraryId}
          onChange={setSelectedLibraryId}
        />
        <p className={planningStyles.safety}>{healthCopy.run.safety}</p>
        <Button
          disabled={
            mutation.isPending ||
            operationGuard.hasActiveOperation ||
            bootstrap?.runtime_capabilities.can_start_operations !== true
          }
          type="submit"
          variant="primary"
        >
          {mutation.isPending ? healthCopy.run.starting : healthCopy.run.submit}
        </Button>
        {mutation.isError ? (
          <PlanningMutationError error={mutation.error} />
        ) : null}
      </form>
      {mutation.data && bootstrap ? (
        <OperationStatus
          initialOperation={mutation.data}
          onSucceeded={refreshFindings}
          onTerminal={operationGuard.recordTerminalOperation}
          policy={bootstrap.operation_polling}
          resultAction={checkResultAction}
        />
      ) : null}
    </section>
  );
}

function checkResultAction(result: OperationResultResource) {
  if (result.kind !== "check_completed") return null;
  return (
    <p role="status">
      {healthCopy.run.completed(
        result.issue_count,
        result.check_run_ids.length,
      )}
    </p>
  );
}
