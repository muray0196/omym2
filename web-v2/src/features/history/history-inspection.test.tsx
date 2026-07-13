/**
 * Summary: Tests Run evidence, capability-driven Undo planning, and durable recovery.
 * Why: Protects pending/manual-review UX while routing reversals through reviewed Plans.
 */
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopeFileEventFacetsData,
  ApiEnvelopeFileEventGroupsData,
  ApiEnvelopePaginatedDataFileEventResource,
  ApiEnvelopeRunDetailData,
  ApiFailureEnvelope,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as RunDetailRoute } from "../../routes/history/detail-route";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import {
  OPERATION_ID,
  completedPlanOperation,
  queuedOperation,
} from "../../test/fixtures/operations";
import { server } from "../../test/server";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { eventStatusLabel, runStatusLabel } from "./history-catalog";

const RUN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345701";

describe("Run detail inspection", () => {
  it("shows pending mutation evidence and a disabled Undo control with recovery", async () => {
    server.use(
      http.get("*/api/history/:runId", () => HttpResponse.json(runDetail)),
      http.get("*/api/history/:runId/events", () =>
        HttpResponse.json(runEvents),
      ),
      http.get("*/api/history/:runId/events/facets", () =>
        HttpResponse.json(eventFacets),
      ),
      http.get("*/api/history/:runId/events/groups", () =>
        HttpResponse.json(eventGroups),
      ),
    );
    renderRoute(`/history/${RUN_ID}`);

    expect(
      await screen.findByRole("heading", { name: "Run detail" }),
    ).toBeVisible();
    expect(screen.getAllByText("Pending — outcome unknown")).toHaveLength(2);
    expect(screen.getByText(/review this event manually/i)).toBeVisible();
    expect(
      screen.getByText(/pending FileEvent requires manual review/i),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Create Undo Plan" }),
    ).toBeDisabled();
    expect(screen.getByRole("link", { name: "Open Health" })).toHaveAttribute(
      "href",
      "/health",
    );
    expect(
      screen.getByRole("link", { name: "Recover active Operation" }),
    ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);
  });

  it("starts Undo planning once, polls it, and opens the resulting Plan review", async () => {
    const undoHeaders: Headers[] = [];
    let operationReads = 0;
    server.use(
      http.get("*/api/history/:runId", () =>
        HttpResponse.json(eligibleRunDetail),
      ),
      http.get("*/api/history/:runId/events", () =>
        HttpResponse.json(runEvents),
      ),
      http.get("*/api/history/:runId/events/facets", () =>
        HttpResponse.json(eventFacets),
      ),
      http.get("*/api/history/:runId/events/groups", () =>
        HttpResponse.json(eventGroups),
      ),
      http.post("*/api/history/:runId/undo-plan", ({ request }) => {
        undoHeaders.push(request.headers);
        return HttpResponse.json(queuedOperation("undo_plan"), { status: 202 });
      }),
      http.get("*/api/operations/:operationId", () => {
        operationReads += 1;
        return HttpResponse.json(completedPlanOperation("undo_plan"));
      }),
    );
    const { user } = renderRoute(`/history/${RUN_ID}`);

    await user.click(
      await screen.findByRole("button", { name: "Create Undo Plan" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Undo Plan review" }),
    ).toBeVisible();
    expect(operationReads).toBe(1);
    expect(undoHeaders[0]?.get("X-OMYM2-CSRF-Token")).toBe(
      normalBootstrap.data.csrf_token,
    );
    expect(undoHeaders[0]?.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("keeps Undo disabled after reloading a capable Run with an active Operation", async () => {
    server.use(
      http.get("*/api/history/:runId", () =>
        HttpResponse.json(eligibleRunWithActiveOperation),
      ),
      http.get("*/api/history/:runId/events", () =>
        HttpResponse.json(runEvents),
      ),
      http.get("*/api/history/:runId/events/facets", () =>
        HttpResponse.json(eventFacets),
      ),
      http.get("*/api/history/:runId/events/groups", () =>
        HttpResponse.json(eventGroups),
      ),
    );
    renderRoute(`/history/${RUN_ID}`);

    expect(
      await screen.findByRole("button", { name: "Create Undo Plan" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("link", { name: "Recover active Operation" }),
    ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);
  });

  it("refetches Run capabilities and Bootstrap after an Undo race error", async () => {
    let attempts = 0;
    let bootstrapReads = 0;
    let detailEnvelope: ApiEnvelopeRunDetailData = eligibleRunDetail;
    server.use(
      http.get("*/api/bootstrap", () => {
        bootstrapReads += 1;
        return HttpResponse.json(normalBootstrap);
      }),
      http.get("*/api/history/:runId", () => HttpResponse.json(detailEnvelope)),
      http.get("*/api/history/:runId/events", () =>
        HttpResponse.json(runEvents),
      ),
      http.get("*/api/history/:runId/events/facets", () =>
        HttpResponse.json(eventFacets),
      ),
      http.get("*/api/history/:runId/events/groups", () =>
        HttpResponse.json(eventGroups),
      ),
      http.post("*/api/history/:runId/undo-plan", () => {
        attempts += 1;
        detailEnvelope = runDetail;
        return HttpResponse.json(undoConflict, { status: 409 });
      }),
    );
    const { user } = renderRoute(`/history/${RUN_ID}`, true);

    await waitFor(() => expect(bootstrapReads).toBe(1));
    await user.click(
      await screen.findByRole("button", { name: "Create Undo Plan" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveFocus();
    expect(alert).toHaveTextContent("Another Operation claimed this Run.");
    expect(attempts).toBe(1);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Create Undo Plan" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("link", { name: "Recover active Operation" }),
      ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);
      expect(bootstrapReads).toBe(2);
    });
  });

  it("preserves raw unknown catalog values", () => {
    expect(runStatusLabel("future_run_state")).toBe(
      "Unknown status: future_run_state",
    );
    expect(eventStatusLabel("future_event_state")).toBe(
      "Unknown status: future_event_state",
    );
  });

  it("renders the typed Run not-found state", async () => {
    server.use(
      http.get("*/api/history/:runId", () =>
        HttpResponse.json(
          {
            data: null,
            errors: [
              {
                code: "run_not_found",
                message: "Run was not found.",
                field: "path.run_id",
                retryable: false,
              },
            ],
          },
          { status: 404 },
        ),
      ),
      http.get("*/api/history/:runId/events", () =>
        HttpResponse.json(runEvents),
      ),
      http.get("*/api/history/:runId/events/facets", () =>
        HttpResponse.json(eventFacets),
      ),
      http.get("*/api/history/:runId/events/groups", () =>
        HttpResponse.json(eventGroups),
      ),
    );
    renderRoute(`/history/${RUN_ID}`);

    expect(
      await screen.findByText(/not available in recorded History/i),
    ).toBeVisible();
  });
});

function renderRoute(initialEntry: string, observeBootstrap = false) {
  const router = createMemoryRouter(
    [
      { path: "/history/:runId", Component: RunDetailRoute },
      {
        path: "/plans/:planId",
        element: <RouteHeading>Undo Plan review</RouteHeading>,
      },
    ],
    { initialEntries: [initialEntry] },
  );
  return {
    router,
    user: userEvent.setup(),
    ...render(
      <QueryClientProvider client={createQueryClient()}>
        {observeBootstrap ? <BootstrapQueryObserver /> : null}
        <BootstrapContext value={normalBootstrap.data}>
          <RouterProvider router={router} />
        </BootstrapContext>
      </QueryClientProvider>,
    ),
  };
}

function BootstrapQueryObserver() {
  useQuery(bootstrapQuery);
  return null;
}

const runDetail = {
  data: {
    run: {
      run_id: RUN_ID,
      plan_id: "018f6a4f-3c2d-7b8a-9abc-def012345702",
      library_id: "018f6a4f-3c2d-7b8a-9abc-def012345703",
      status: "partial_failed",
      started_at: "2026-07-13T00:00:00Z",
      completed_at: "2026-07-13T00:01:00Z",
      error_summary: "One move is unconfirmed.",
    },
    capabilities: {
      can_create_undo: false,
      disabled_reasons: [
        {
          code: "pending_file_event_requires_review",
          message: "A pending FileEvent requires manual review.",
          field: "capabilities.can_create_undo",
          retryable: false,
          remediation: { label: "Open Health", route: "/health" },
        },
      ],
    },
    active_operation_id: OPERATION_ID,
  },
  errors: [],
} satisfies ApiEnvelopeRunDetailData;

const eligibleRunDetail = {
  data: {
    active_operation_id: null,
    capabilities: { can_create_undo: true, disabled_reasons: [] },
    run: {
      ...runDetail.data.run,
      completed_at: "2026-07-13T00:01:00Z",
      error_summary: null,
      status: "succeeded",
    },
  },
  errors: [],
} satisfies ApiEnvelopeRunDetailData;

const eligibleRunWithActiveOperation = {
  ...eligibleRunDetail,
  data: {
    ...eligibleRunDetail.data,
    active_operation_id: OPERATION_ID,
  },
} satisfies ApiEnvelopeRunDetailData;

const undoConflict = {
  data: null,
  errors: [
    {
      code: "operation_in_progress",
      field: "path.run_id",
      message: "Another Operation claimed this Run.",
      remediation: {
        label: "View active Operation",
        route: `/api/operations/${OPERATION_ID}`,
      },
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;

const runEvents = {
  data: {
    items: [
      {
        event_id: "018f6a4f-3c2d-7b8a-9abc-def012345704",
        library_id: runDetail.data.run.library_id,
        run_id: RUN_ID,
        plan_action_id: "018f6a4f-3c2d-7b8a-9abc-def012345705",
        event_type: "move_file",
        source_path: "Old/Track.flac",
        target_path: "New/Track.flac",
        status: "pending",
        started_at: "2026-07-13T00:00:10Z",
        completed_at: null,
        error_code: null,
        error_message: null,
        sequence_no: 1,
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataFileEventResource;

const eventFacets = {
  data: { facets: { status: [{ value: "pending", count: 1 }] }, total: 1 },
  errors: [],
} satisfies ApiEnvelopeFileEventFacetsData;
const eventGroups = {
  data: {
    group_by: "target_directory",
    items: [{ key: "New", label: "New", count: 1 }],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopeFileEventGroupsData;
