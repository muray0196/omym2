/**
 * Summary: Verifies observable Plan list URL filters, cursor paging, and recovery states.
 * Why: Protects inspection browsing from accidental local state or cursor derivation.
 */
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ApiFailureEnvelope } from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { server } from "../../test/server";
import {
  HISTORIC_PLAN_ID,
  OPAQUE_PLAN_CURSOR,
  READY_PLAN_ID,
  emptyPlanPage,
  planListFirstPage,
  planListSecondPage,
} from "../../test/fixtures/plans";
import { PlanList } from "./plan-list";

describe("PlanList", () => {
  it("bounds cursor pages and resets to page one for new URL filters", async () => {
    const observedRequests: URLSearchParams[] = [];
    server.use(
      http.get("*/api/plans", ({ request }) => {
        const parameters = new URL(request.url).searchParams;
        observedRequests.push(parameters);
        return HttpResponse.json(
          parameters.get("cursor") === OPAQUE_PLAN_CURSOR
            ? planListSecondPage
            : planListFirstPage,
        );
      }),
    );
    const { router, user } = renderPlanList();

    expect(screen.getByRole("status")).toHaveTextContent("Loading Plans…");
    await screen.findByText(READY_PLAN_ID);

    await user.click(
      screen.getByRole("button", { name: "Next page of Plans" }),
    );
    await screen.findByText(HISTORIC_PLAN_ID);
    expect(screen.queryByText(READY_PLAN_ID)).not.toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2")).toBeVisible();
    expect(
      observedRequests.some(
        (parameters) => parameters.get("cursor") === OPAQUE_PLAN_CURSOR,
      ),
    ).toBe(true);

    await user.click(
      screen.getByRole("button", { name: "Previous page of Plans" }),
    );
    expect(await screen.findByText(READY_PLAN_ID)).toBeVisible();
    expect(screen.queryByText(HISTORIC_PLAN_ID)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Next page of Plans" }),
    );
    expect(await screen.findByText(HISTORIC_PLAN_ID)).toBeVisible();

    await user.type(
      screen.getByRole("searchbox", { name: "Search Plans" }),
      "ready",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Plan status" }),
      "ready",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Plan type" }),
      "refresh",
    );
    await user.click(
      screen.getByRole("checkbox", { name: "Has blocked actions" }),
    );

    await waitFor(() => {
      const parameters = new URLSearchParams(router.state.location.search);
      expect(parameters.get("query")).toBe("ready");
      expect(parameters.get("status")).toBe("ready");
      expect(parameters.get("type")).toBe("refresh");
      expect(parameters.get("blocked")).toBe("true");
      expect(observedRequests.at(-1)?.get("cursor")).toBeNull();
      expect(screen.getByText("Page 1 of 2")).toBeVisible();
      expect(screen.queryByText(HISTORIC_PLAN_ID)).not.toBeInTheDocument();
    });

    await user.click(
      screen.getAllByRole("button", { name: "Reset filters" })[0]!,
    );
    await waitFor(() => expect(router.state.location.search).toBe(""));
  });

  it("presents an accessible empty result with a filter reset", async () => {
    server.use(http.get("*/api/plans", () => HttpResponse.json(emptyPlanPage)));
    const { user } = renderPlanList("/plans?status=ready");

    expect(
      await screen.findByRole("heading", {
        name: "No Plans match these filters",
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "Plans pagination" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getAllByRole("button", { name: "Reset filters" })[0]!,
    );
    expect(screen.getByRole("searchbox", { name: "Search Plans" })).toHaveValue(
      "",
    );
  });

  it("separates a typed API failure from an empty result", async () => {
    const failure = {
      data: null,
      errors: [
        {
          code: "internal_error",
          message: "Plan storage is temporarily unavailable.",
          retryable: true,
        },
      ],
    } satisfies ApiFailureEnvelope;
    server.use(
      http.get("*/api/plans", () =>
        HttpResponse.json(failure, { status: 500 }),
      ),
    );
    renderPlanList();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Plans could not be loaded");
    expect(alert).toHaveTextContent("Plan storage is temporarily unavailable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});

function renderPlanList(initialEntry = "/plans") {
  const router = createMemoryRouter([{ path: "/plans", Component: PlanList }], {
    initialEntries: [initialEntry],
  });

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
