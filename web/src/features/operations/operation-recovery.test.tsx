/**
 * Summary: Verifies routed Operation recovery, retryable read backoff, and interruption evidence.
 * Why: Keeps accepted work inspectable after reload without resending its mutation.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopeOperationResource,
  ApiFailureEnvelope,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as OperationRecoveryRoute } from "../../routes/operations/detail-route";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import { CREATED_PLAN_ID, OPERATION_ID } from "../../test/fixtures/operations";
import { server } from "../../test/server";

describe("Operation recovery route", () => {
  it("backs off a retryable API read and exposes interrupted Plan evidence", async () => {
    let reads = 0;
    server.use(
      http.get("*/api/operations/:operationId", () => {
        reads += 1;
        if (reads === 1) return HttpResponse.json(activeOperation);
        if (reads === 2)
          return HttpResponse.json(retryableReadFailure, { status: 500 });
        return HttpResponse.json(interruptedOperation);
      }),
    );
    renderRecoveryRoute();

    expect(
      await screen.findByRole("heading", { name: "Operation recovery" }),
    ).toHaveFocus();
    expect((await screen.findAllByText("Running")).length).toBeGreaterThan(0);

    expect(
      await screen.findByText("Operation storage is temporarily busy."),
    ).toBeVisible();

    await waitFor(() => expect(reads).toBe(3));
    expect((await screen.findAllByText("Interrupted")).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByRole("link", { name: "Inspect related Plan" }),
    ).toHaveAttribute("href", `/plans/${CREATED_PLAN_ID}`);
  });
});

function renderRecoveryRoute() {
  const router = createMemoryRouter(
    [
      {
        path: "/operations/:operationId",
        Component: OperationRecoveryRoute,
      },
    ],
    { initialEntries: [`/operations/${OPERATION_ID}`] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <BootstrapContext value={recoveryBootstrap}>
        <RouterProvider router={router} />
      </BootstrapContext>
    </QueryClientProvider>,
  );
}

const recoveryBootstrap = {
  ...normalBootstrap.data,
  operation_polling: {
    backoff_factor: 2,
    initial_ms: 10,
    max_ms: 40,
  },
};

const activeOperation = {
  data: {
    completed_at: null,
    error: null,
    kind: "add_plan",
    library_id: normalBootstrap.data.active_library?.library_id ?? null,
    operation_id: OPERATION_ID,
    plan_id: CREATED_PLAN_ID,
    requested_at: "2026-07-13T00:00:00Z",
    result: null,
    run_id: null,
    started_at: "2026-07-13T00:00:01Z",
    status: "running",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;

const interruptedOperation = {
  data: {
    ...activeOperation.data,
    completed_at: "2026-07-13T00:00:03Z",
    error: {
      code: "operation_interrupted",
      message: "The worker stopped before the Operation completed.",
      retryable: false,
    },
    status: "interrupted",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;

const retryableReadFailure = {
  data: null,
  errors: [
    {
      code: "storage_unavailable",
      message: "Operation storage is temporarily busy.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;
