/**
 * Summary: Polls retained Operations with backend-provided adaptive timing.
 * Why: Preserves durable progress across slow work and transient connectivity loss.
 */
import { useEffect, useMemo, useState } from "react";
import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getOperation,
  type ApiFailureEnvelope,
  type OperationPollingPolicy,
  type OperationRef,
  type OperationResource,
} from "../../api/generated";
import {
  OperationApiError,
  OperationTransportError,
  OperationUnexpectedDataError,
} from "./operation-start";

export type OperationConnectivity = "connected" | "disconnected";

export function useOperationPolling({
  initialOperation,
  policy,
}: {
  initialOperation: OperationRef | OperationResource | null;
  policy: OperationPollingPolicy;
}) {
  const operationId = initialOperation?.operation_id ?? null;
  const queryClient = useQueryClient();
  const options = useMemo(
    () => operationQuery(operationId ?? "disabled"),
    [operationId],
  );
  const query = useQuery({
    ...options,
    enabled: false,
  });
  const [connectivity, setConnectivity] =
    useState<OperationConnectivity>("connected");

  useEffect(() => {
    if (operationId === null) return;
    if (
      initialOperation !== null &&
      "progress" in initialOperation &&
      isTerminalOperation(initialOperation)
    )
      return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = policy.initial_ms;
    let previousSnapshot = operationSnapshot(initialOperation);

    const schedule = (nextDelay: number) => {
      timer = setTimeout(() => void poll(), nextDelay);
    };

    const poll = async () => {
      try {
        const operation = await queryClient.fetchQuery(options);
        if (cancelled) return;
        setConnectivity("connected");
        if (isTerminalOperation(operation)) return;

        const snapshot = operationSnapshot(operation);
        delay =
          snapshot === previousSnapshot
            ? cappedBackoff(delay, policy)
            : policy.initial_ms;
        previousSnapshot = snapshot;
        schedule(delay);
      } catch (error) {
        if (cancelled) return;
        if (error instanceof OperationTransportError) {
          setConnectivity("disconnected");
          delay = cappedBackoff(delay, policy);
          schedule(delay);
          return;
        }
        if (isRetryableOperationReadError(error)) {
          setConnectivity("connected");
          delay = cappedBackoff(delay, policy);
          schedule(delay);
        }
      }
    };

    schedule(policy.initial_ms);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [initialOperation, operationId, options, policy, queryClient]);

  return { ...query, connectivity };
}

export function operationQuery(operationId: string) {
  return queryOptions({
    queryKey: ["operations", operationId] as const,
    queryFn: () => readOperation(operationId),
    retry: false,
    staleTime: 0,
  });
}

export function operationRecoveryQuery(operationId: string) {
  return queryOptions({
    enabled: operationId.length > 0,
    queryFn: () => readOperation(operationId),
    queryKey: ["operations", operationId, "recovery"] as const,
    retry: false,
  });
}

async function readOperation(operationId: string): Promise<OperationResource> {
  const response = await getOperation({
    baseUrl: globalThis.location.origin,
    path: { operation_id: operationId },
  });
  if (response.error !== undefined) {
    if (response.response === undefined) {
      throw new OperationTransportError();
    }
    throw new OperationApiError(response.error, response.response.status);
  }
  const operation = response.data?.data;
  if (operation === null || operation === undefined) {
    throw new OperationUnexpectedDataError();
  }
  return operation;
}

function cappedBackoff(currentDelay: number, policy: OperationPollingPolicy) {
  return Math.min(currentDelay * policy.backoff_factor, policy.max_ms);
}

function operationSnapshot(operation: OperationRef | OperationResource | null) {
  if (operation === null) return "";
  if (!("progress" in operation)) return operation.status;
  return JSON.stringify([
    operation.status,
    operation.progress.stage_code,
    operation.progress.completed_units,
    operation.progress.total_units,
    operation.progress.message,
    operation.result,
    operation.error,
  ]);
}

export function isTerminalOperation(operation: OperationResource) {
  return (
    operation.status === "succeeded" ||
    operation.status === "failed" ||
    operation.status === "interrupted"
  );
}

export function isActiveOperation(
  operation: OperationRef | OperationResource | undefined,
) {
  return operation?.status === "queued" || operation?.status === "running";
}

export function isRetryableOperationReadError(error: unknown) {
  return (
    error instanceof OperationApiError &&
    error.status >= 500 &&
    error.envelope.errors.some((diagnostic) => diagnostic.retryable)
  );
}

export function operationPollingErrors(
  error: Error | null,
): ApiFailureEnvelope["errors"] {
  return error instanceof OperationApiError ? error.envelope.errors : [];
}
