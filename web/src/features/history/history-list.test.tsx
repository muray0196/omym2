/**
 * Summary: Verifies bounded Run cursor pages and filter-driven paging resets.
 * Why: Prevents long History sessions from retaining every fetched Run row in the DOM.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopePaginatedDataRunHeader,
  ApiEnvelopeRunFacetsData,
  RunHeader,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as HistoryListRoute } from "../../routes/history/list-route";
import { server } from "../../test/server";

const FIRST_RUN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345701";
const SECOND_RUN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345702";
const HISTORY_CURSOR = "opaque-history-cursor";

describe("History list", () => {
  it("renders one Run page and resets to page one when filters change", async () => {
    const cursors: Array<string | null> = [];
    server.use(
      http.get("*/api/history", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        cursors.push(cursor);
        return HttpResponse.json(
          cursor === null ? firstRunPage : secondRunPage,
        );
      }),
      http.get("*/api/history/facets", () => HttpResponse.json(runFacets)),
    );
    const user = userEvent.setup();
    renderHistoryList();

    expect(await screen.findByText(FIRST_RUN_ID)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next page of Runs" }));

    expect(await screen.findByText(SECOND_RUN_ID)).toBeVisible();
    expect(screen.queryByText(FIRST_RUN_ID)).not.toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeVisible();
    expect(cursors).toEqual([null, HISTORY_CURSOR]);

    await user.type(
      screen.getByRole("searchbox", { name: "Search Runs" }),
      "first",
    );

    expect(await screen.findByText(FIRST_RUN_ID)).toBeVisible();
    expect(screen.queryByText(SECOND_RUN_ID)).not.toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeVisible();
    await waitFor(() => expect(cursors.at(-1)).toBeNull());

    await user.clear(screen.getByRole("searchbox", { name: "Search Runs" }));

    expect(await screen.findByText(FIRST_RUN_ID)).toBeVisible();
    expect(screen.queryByText(SECOND_RUN_ID)).not.toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeVisible();
  });
});

function renderHistoryList() {
  const router = createMemoryRouter(
    [{ path: "/history", Component: HistoryListRoute }],
    { initialEntries: ["/history"] },
  );
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function runPage(
  items: RunHeader[],
  nextCursor: string | null,
): ApiEnvelopePaginatedDataRunHeader {
  return {
    data: {
      items,
      page: { limit: 1, next_cursor: nextCursor, total: 2 },
    },
    errors: [],
  };
}

const firstRun = {
  completed_at: "2026-07-13T00:01:00Z",
  error_summary: null,
  library_id: "018f6a4f-3c2d-7b8a-9abc-def012345710",
  plan_id: "018f6a4f-3c2d-7b8a-9abc-def012345720",
  run_id: FIRST_RUN_ID,
  started_at: "2026-07-13T00:00:00Z",
  status: "succeeded",
} satisfies RunHeader;
const secondRun = {
  ...firstRun,
  run_id: SECOND_RUN_ID,
  status: "failed",
} satisfies RunHeader;
const firstRunPage = runPage([firstRun], HISTORY_CURSOR);
const secondRunPage = runPage([secondRun], null);
const runFacets = {
  data: {
    facets: { status: [{ count: 1, value: "succeeded" }] },
    total: 2,
  },
  errors: [],
} satisfies ApiEnvelopeRunFacetsData;
