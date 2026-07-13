/**
 * Summary: Starts durable Operations with shared idempotency and safe CSRF recovery.
 * Why: Keeps every planning and Check mutation within the frozen retry contract.
 */
import type { QueryClient } from "@tanstack/react-query";

import type {
  ApiEnvelopeOperationRef,
  ApiEnvelopeOperationResource,
  ApiFailureEnvelope,
  OperationRef,
  OperationResource,
} from "../../api/generated";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";

type OperationEnvelope = ApiEnvelopeOperationRef | ApiEnvelopeOperationResource;

export type OperationStartResult = OperationRef | OperationResource;

export type OperationStartResponse = {
  data?: OperationEnvelope;
  error?: ApiFailureEnvelope;
  response?: Response;
};

export type OperationHeaders = {
  "Idempotency-Key": string;
  "X-OMYM2-CSRF-Token": string;
};

export class OperationApiError extends Error {
  readonly envelope: ApiFailureEnvelope;
  readonly status: number;

  constructor(envelope: ApiFailureEnvelope, status: number) {
    super("The Operation request returned a typed API failure.");
    this.name = "OperationApiError";
    this.envelope = envelope;
    this.status = status;
  }
}

export class OperationTransportError extends Error {
  constructor() {
    super("The local service could not be reached.");
    this.name = "OperationTransportError";
  }
}

export class OperationUnexpectedDataError extends Error {
  constructor() {
    super("The Operation request returned no readable resource.");
    this.name = "OperationUnexpectedDataError";
  }
}

export async function startOperationSafely({
  csrfToken,
  keyFactory = () => globalThis.crypto.randomUUID(),
  queryClient,
  send,
}: {
  csrfToken: string;
  keyFactory?: () => string;
  queryClient: QueryClient;
  send: (headers: OperationHeaders) => Promise<OperationStartResponse>;
}): Promise<OperationStartResult> {
  const idempotencyKey = keyFactory();
  const firstResponse = await send({
    "Idempotency-Key": idempotencyKey,
    "X-OMYM2-CSRF-Token": csrfToken,
  });

  if (!isCsrfInvalid(firstResponse)) {
    return operationOrThrow(firstResponse);
  }

  await queryClient.invalidateQueries({
    queryKey: bootstrapQuery.queryKey,
    refetchType: "none",
  });
  const refreshedBootstrap = await queryClient.fetchQuery(bootstrapQuery);
  const refreshedToken = refreshedBootstrap.data?.csrf_token;
  if (refreshedToken === undefined) {
    throw new OperationUnexpectedDataError();
  }

  const retriedResponse = await send({
    "Idempotency-Key": idempotencyKey,
    "X-OMYM2-CSRF-Token": refreshedToken,
  });
  return operationOrThrow(retriedResponse);
}

function isCsrfInvalid(response: OperationStartResponse): boolean {
  return (
    response.response?.status === 403 &&
    response.error?.errors.some((error) => error.code === "csrf_invalid") ===
      true
  );
}

function operationOrThrow(
  response: OperationStartResponse,
): OperationStartResult {
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
