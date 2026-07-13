/**
 * Summary: Defines shared read-only inspection query failures.
 * Why: Keeps typed API diagnostics distinct from local transport failures.
 */
import type { ApiFailureEnvelope } from "../../api/generated";

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
