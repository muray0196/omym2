/**
 * Summary: Verifies durable Operation idempotency and the single safe CSRF retry.
 * Why: Prevents mutation retries from duplicating planning or Check side effects.
 */
import { QueryClient } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { ApiFailureEnvelope } from "../../api/generated";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import { queuedOperation } from "../../test/fixtures/operations";
import { server } from "../../test/server";
import {
  OperationTransportError,
  startOperationSafely,
  type OperationHeaders,
} from "./operation-start";

describe("startOperationSafely", () => {
  it("refreshes Bootstrap once after csrf_invalid and resends the identical key", async () => {
    const headers: OperationHeaders[] = [];
    const send = vi.fn((requestHeaders: OperationHeaders) => {
      headers.push(requestHeaders);
      if (headers.length === 1) {
        return Promise.resolve({
          error: csrfFailure,
          response: new Response(null, { status: 403 }),
        });
      }
      return Promise.resolve({
        data: queuedOperation(),
        response: new Response(null, { status: 202 }),
      });
    });
    server.use(
      http.get("*/api/bootstrap", () =>
        HttpResponse.json({
          ...normalBootstrap,
          data: { ...normalBootstrap.data, csrf_token: "refreshed-token" },
        }),
      ),
    );

    const operation = await startOperationSafely({
      csrfToken: "expired-token",
      keyFactory: () => "018f0000-0000-7000-8000-000000000099",
      queryClient: new QueryClient(),
      send,
    });

    expect(operation.operation_id).toBe(queuedOperation().data.operation_id);
    expect(send).toHaveBeenCalledTimes(2);
    expect(headers).toEqual([
      {
        "Idempotency-Key": "018f0000-0000-7000-8000-000000000099",
        "X-OMYM2-CSRF-Token": "expired-token",
      },
      {
        "Idempotency-Key": "018f0000-0000-7000-8000-000000000099",
        "X-OMYM2-CSRF-Token": "refreshed-token",
      },
    ]);
  });

  it("does not retry a connectivity failure", async () => {
    const send = vi.fn(() => Promise.resolve({ error: csrfFailure }));

    await expect(
      startOperationSafely({
        csrfToken: "fixture-token",
        keyFactory: () => "018f0000-0000-7000-8000-000000000099",
        queryClient: new QueryClient(),
        send,
      }),
    ).rejects.toBeInstanceOf(OperationTransportError);
    expect(send).toHaveBeenCalledOnce();
  });
});

const csrfFailure = {
  data: null,
  errors: [
    {
      code: "csrf_invalid",
      message: "Refresh Bootstrap and try again.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;
