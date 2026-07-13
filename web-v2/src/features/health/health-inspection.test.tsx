/**
 * Summary: Tests persisted Health freshness, group drill-down, and pending review guidance.
 * Why: Ensures GET-only inspection stays URL-addressable and never exposes Run Check.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopeCheckIssueFacetsData,
  ApiEnvelopeCheckIssueGroupsData,
  ApiEnvelopeCheckIssuesData,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as HealthRoute } from "../../routes/health/route";
import { server } from "../../test/server";
import { issueTypeLabel } from "./health-catalog";

describe("Health inspection", () => {
  it("drills into an opaque server group and keeps Check execution unavailable", async () => {
    let drillDownSeen = false;
    server.use(
      http.get("*/api/check", ({ request }) => {
        const url = new URL(request.url);
        drillDownSeen ||=
          url.searchParams.get("group_by") === "severity" &&
          url.searchParams.get("group_key") === "warning";
        return HttpResponse.json(checkIssues);
      }),
      http.get("*/api/check/facets", () => HttpResponse.json(checkFacets)),
      http.get("*/api/check/groups", () => HttpResponse.json(checkGroups)),
    );
    const { router } = renderRoute("/health?group_by=severity");

    expect(await screen.findByText(/no automatic repair/i)).toBeVisible();
    expect(
      screen.getAllByText("Pending FileEvent requires review").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Findings checked/i)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Warnings/i }));

    await waitFor(() => expect(drillDownSeen).toBe(true));
    expect(router.state.location.search).toContain("group_key=warning");
    expect(
      screen.queryByRole("button", { name: /run check/i }),
    ).not.toBeInTheDocument();
  });

  it("preserves a raw unknown issue value", () => {
    expect(issueTypeLabel("future_issue")).toBe(
      "Unknown issue type: future_issue",
    );
  });
});

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: "/health", Component: HealthRoute }],
    { initialEntries: [initialEntry] },
  );
  return {
    router,
    ...render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}

const checkIssues = {
  data: {
    checked_at: "2026-07-13T00:00:00Z",
    items: [
      {
        issue_type: "pending_file_event_exists",
        library_id: "018f6a4f-3c2d-7b8a-9abc-def012345711",
        path: "Artist/Track.flac",
        track_id: null,
        plan_id: "018f6a4f-3c2d-7b8a-9abc-def012345712",
        detail: "A prior mutation has no confirmed outcome.",
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssuesData;
const checkFacets = {
  data: {
    checked_at: "2026-07-13T00:00:00Z",
    facets: { issue_type: [{ value: "pending_file_event_exists", count: 1 }] },
    total: 1,
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueFacetsData;
const checkGroups = {
  data: {
    group_by: "severity",
    items: [
      {
        key: "warning",
        label: "Warnings",
        count: 1,
        common_path_root: "Artist/",
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueGroupsData;
