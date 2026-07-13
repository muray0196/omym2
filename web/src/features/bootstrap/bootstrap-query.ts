/**
 * Summary: Defines the deduplicated typed Bootstrap query.
 * Why: Uses generated SDK output as the sole initial-state transport contract.
 */
import { queryOptions } from "@tanstack/react-query";

import { getBootstrap, type ApiFailureEnvelope } from "../../api/generated";

export class BootstrapApiError extends Error {
  readonly envelope: ApiFailureEnvelope;

  constructor(envelope: ApiFailureEnvelope) {
    super("Bootstrap returned a typed API failure.");
    this.name = "BootstrapApiError";
    this.envelope = envelope;
  }
}

export class BootstrapTransportError extends Error {
  constructor() {
    super("Bootstrap could not reach the local service.");
    this.name = "BootstrapTransportError";
  }
}

export const bootstrapQuery = queryOptions({
  queryKey: ["bootstrap"] as const,
  queryFn: async () => {
    const response = await getBootstrap({
      baseUrl: globalThis.location.origin,
    });
    if (response.error !== undefined) {
      if (response.response !== undefined) {
        throw new BootstrapApiError(response.error);
      }
      throw new BootstrapTransportError();
    }
    return response.data;
  },
});
