/**
 * Summary: Tests read-only Run detail evidence and unknown-value presentation.
 * Why: Protects pending/manual-review UX while keeping Undo unavailable before M4.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopeFileEventFacetsData,
  ApiEnvelopeFileEventGroupsData,
  ApiEnvelopePaginatedDataFileEventResource,
  ApiEnvelopeRunDetailData,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as RunDetailRoute } from "../../routes/history/detail-route";
import { server } from "../../test/server";
import { eventStatusLabel, runStatusLabel } from "./history-catalog";

const RUN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345701";

describe("Run detail inspection", () => {
  it("shows pending mutation evidence and backend refusal without an Undo control", async () => {
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
      screen.queryByRole("button", { name: /undo/i }),
    ).not.toBeInTheDocument();
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

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: "/history/:runId", Component: RunDetailRoute }],
    { initialEntries: [initialEntry] },
  );
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
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
    active_operation_id: null,
  },
  errors: [],
} satisfies ApiEnvelopeRunDetailData;

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
