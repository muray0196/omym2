/**
 * Summary: Defines shared read-only inspection query failures.
 * Why: Keeps typed API diagnostics distinct from local transport failures.
 */
import type { ApiErrorCode, ApiFailureEnvelope } from "../../api/generated";

export class InspectionApiError extends Error {
  readonly envelope: ApiFailureEnvelope;

  constructor(surface: string, envelope: ApiFailureEnvelope) {
    super(`${surface} returned a typed API failure.`);
    this.name = "InspectionApiError";
    this.envelope = envelope;
  }
}

export class InspectionTransportError extends Error {
  constructor(surface: string) {
    super(`${surface} could not reach the local service.`);
    this.name = "InspectionTransportError";
  }
}

export class InspectionUnexpectedDataError extends Error {
  constructor(surface: string) {
    super(`${surface} returned no readable data.`);
    this.name = "InspectionUnexpectedDataError";
  }
}

export function throwInspectionResponseError(
  surface: string,
  envelope: ApiFailureEnvelope,
  response: Response | undefined,
): never {
  if (response === undefined) {
    throw new InspectionTransportError(surface);
  }
  throw new InspectionApiError(surface, envelope);
}

export function inspectionDataOrThrow<Data>(
  response: {
    data?: { data: Data | null };
    error?: ApiFailureEnvelope;
    response?: Response;
  },
  surface: string,
): Data {
  if (response.error !== undefined) {
    throwInspectionResponseError(surface, response.error, response.response);
  }
  const data = response.data?.data;
  if (data == null) {
    throw new InspectionUnexpectedDataError(surface);
  }
  return data;
}

export function inspectionErrorHasCode(error: Error, code: ApiErrorCode) {
  return (
    error instanceof InspectionApiError &&
    error.envelope.errors.some((diagnostic) => diagnostic.code === code)
  );
}
