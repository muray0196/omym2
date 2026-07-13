/**
 * Summary: Verifies deep Plan inspection uses exact list lookup and independent evidence reads.
 * Why: Prevents M2 detail links from reaching capability or mutation-oriented transport.
 */
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { createQueryClient } from "../../app/query-client";
import { server } from "../../test/server";
import {
  OPAQUE_ACTION_CURSOR,
  READY_PLAN_ID,
  emptyPlanPage,
  exactReadyPlanPage,
  readyPlanActionsFirstPage,
  readyPlanActionsSecondPage,
  readyPlanFacets,
  readyPlanGroupsFirstPage,
} from "../../test/fixtures/plans";
import { PlanDetail } from "./plan-detail";

describe("PlanDetail", () => {
  it("loads typed detail and independent actions, facets, and groups", async () => {
    const actionCursors: Array<string | null> = [];
    server.use(
      http.get("*/api/plans", () => HttpResponse.json(exactReadyPlanPage)),
      http.get("*/api/plans/:planId/actions", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        actionCursors.push(cursor);
        return HttpResponse.json(
          cursor === OPAQUE_ACTION_CURSOR
            ? readyPlanActionsSecondPage
            : readyPlanActionsFirstPage,
        );
      }),
      http.get("*/api/plans/:planId/facets", () =>
        HttpResponse.json(readyPlanFacets),
      ),
      http.get("*/api/plans/:planId/groups", () =>
        HttpResponse.json(readyPlanGroupsFirstPage),
      ),
    );
    const { router, user } = renderPlanDetail();

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading Plan detail…",
    );
    await screen.findByRole("heading", { name: "Plan detail" });
    await screen.findByRole("heading", { name: "Recorded action summary" });
    await screen.findByText("Action facets");
    await screen.findByText("Action groups");

    expect(
      screen.getByText("01912345-6789-7abc-8def-012345678911"),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Load more actions" }));
    await waitFor(() => expect(actionCursors).toContain(OPAQUE_ACTION_CURSOR));

    await user.click(screen.getByRole("button", { name: /^Planned/ }));
    await waitFor(() => {
      const parameters = new URLSearchParams(router.state.location.search);
      expect(parameters.get("group_key")).toBe("fixture-group-planned");
    });
  });

  it("renders an accessible not-found state when the exact full-ID list lookup is empty", async () => {
    const missingPlanId = "01912345-6789-7abc-8def-012345678999";
    server.use(http.get("*/api/plans", () => HttpResponse.json(emptyPlanPage)));
    renderPlanDetail(`/plans/${missingPlanId}`);

    expect(
      await screen.findByRole("heading", { name: "Plan not found" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to Plans" })).toHaveAttribute(
      "href",
      "/plans",
    );
  });
});

function renderPlanDetail(initialEntry = `/plans/${READY_PLAN_ID}`) {
  const router = createMemoryRouter(
    [{ path: "/plans/:planId", Component: PlanDetail }],
    { initialEntries: [initialEntry] },
  );

  return {
    router,
    user: userEvent.setup(),
    ...render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}
