/**
 * Summary: Tests Plan browsing and exact review against typed MSW responses.
 * Why: Protects URL filters, opaque pagination, execution visibility, and recorded evidence.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopePaginatedDataPlanActionResource,
  ApiEnvelopePaginatedDataPlanSummary,
  ApiEnvelopePlanActionFacetsData,
  ApiEnvelopePlanActionGroupsData,
  ApiEnvelopePlanDetailData,
  ApiFailureEnvelope,
  PlanActionResource,
  PlanActionSummary,
  PlanSummary,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import { server } from "../../test/server";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { PlanDetail } from "./plan-detail";
import { PlanList } from "./plan-list";

const PLAN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345671";
const SECOND_PLAN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345672";
const ACTION_ID = "018f6a4f-3c2d-7b8a-9abc-def012345673";
const SECOND_ACTION_ID = "018f6a4f-3c2d-7b8a-9abc-def012345674";
const LIBRARY_ID = "018f6a4f-3c2d-7b8a-9abc-def012345670";
const OPAQUE_PLAN_CURSOR = "opaque-plan-cursor";
const OPAQUE_ACTION_CURSOR = "opaque-action-cursor";

describe("Plan inspection", () => {
  it("owns list filters in the URL and passes opaque cursors unchanged", async () => {
    const seenCursors: Array<string | null> = [];
    const seenQueries: URLSearchParams[] = [];
    server.use(
      http.get("*/api/plans", ({ request }) => {
        const query = new URL(request.url).searchParams;
        seenQueries.push(query);
        seenCursors.push(query.get("cursor"));
        return HttpResponse.json(
          query.get("cursor") === OPAQUE_PLAN_CURSOR
            ? planListEnvelope([secondPlan], null)
            : planListEnvelope([readyPlan], OPAQUE_PLAN_CURSOR),
        );
      }),
    );
    const { router, user } = renderPlanList(
      "/plans?query=ready&status=ready&type=add&blocked=true",
    );

    expect(await screen.findByText(PLAN_ID)).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search Plans" })).toHaveValue(
      "ready",
    );
    expect(screen.getByRole("combobox", { name: "Plan status" })).toHaveValue(
      "ready",
    );
    expect(screen.getByRole("combobox", { name: "Plan type" })).toHaveValue(
      "add",
    );
    expect(
      screen.getByRole("checkbox", { name: "Has blocked actions" }),
    ).toBeChecked();
    expect(seenQueries[0]?.get("blocked")).toBe("true");

    await user.click(
      screen.getByRole("button", { name: "Next page of Plans" }),
    );

    expect(await screen.findByText(SECOND_PLAN_ID)).toBeVisible();
    expect(screen.queryByText(PLAN_ID)).not.toBeInTheDocument();
    expect(seenCursors).toContain(OPAQUE_PLAN_CURSOR);

    await user.selectOptions(
      screen.getByRole("combobox", { name: "Plan status" }),
      "failed",
    );
    await waitFor(() =>
      expect(router.state.location.search).toContain("status=failed"),
    );
  });

  it("round-trips Plan list URL state through detail and Back", async () => {
    server.use(
      http.get("*/api/plans", () =>
        HttpResponse.json(planListEnvelope([readyPlan], null)),
      ),
      ...detailHandlers(new Set<string>(), []),
    );
    const initialSearch = "?query=ready&status=ready&type=add&blocked=true";
    const { router, user } = renderPlanRoundTrip(`/plans${initialSearch}`);

    await user.click(
      await screen.findByRole("link", { name: new RegExp(PLAN_ID) }),
    );

    expect(router.state.location.pathname).toBe(`/plans/${PLAN_ID}`);
    expect(router.state.location.search).toBe(initialSearch);
    const back = await screen.findByRole("link", { name: "Back to Plans" });
    expect(back).toHaveAttribute("href", `/plans${initialSearch}`);
    await user.click(back);

    expect(await screen.findByRole("heading", { name: "Plans" })).toBeVisible();
    expect(router.state.location.search).toBe(initialSearch);
    expect(screen.getByRole("searchbox", { name: "Search Plans" })).toHaveValue(
      "ready",
    );
    expect(screen.getByRole("combobox", { name: "Plan status" })).toHaveValue(
      "ready",
    );
  });

  it("renders loading, filtered-empty, and typed error states distinctly", async () => {
    let resolveRequest: (() => void) | undefined;
    const pendingRequest = new Promise<void>((resolve) => {
      resolveRequest = resolve;
    });
    server.use(
      http.get("*/api/plans", async () => {
        await pendingRequest;
        return HttpResponse.json(planListEnvelope([], null));
      }),
    );
    const loadingView = renderPlanList("/plans?status=failed");

    expect(screen.getByRole("status")).toHaveTextContent("Loading Plans");
    resolveRequest?.();
    expect(
      await screen.findByRole("heading", {
        name: "No Plans match these filters",
      }),
    ).toBeVisible();
    loadingView.unmount();

    server.use(
      http.get("*/api/plans", () =>
        HttpResponse.json(storageFailure, { status: 500 }),
      ),
    );
    renderPlanList();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Plan storage is unavailable.",
    );
  });

  it("loads detail evidence in parallel and paginates recorded actions", async () => {
    const requestedPaths = new Set<string>();
    const actionCursors: Array<string | null> = [];
    server.use(...detailHandlers(requestedPaths, actionCursors));
    const { router, user } = renderPlanDetail(
      `/plans/${PLAN_ID}?action_status=blocked`,
    );

    expect(await screen.findByText(PLAN_ID)).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Recorded action summary" }),
    ).toBeVisible();
    expect(await screen.findByText(ACTION_ID)).toBeVisible();
    expect(screen.getByText(/Recorded target collisions/)).toBeVisible();
    const groupButton = within(
      await screen.findByRole("list", { name: "Action groups" }),
    ).getByRole("button");
    expect(groupButton).toHaveTextContent("Blocked");
    expect(requestedPaths).toEqual(
      new Set([
        `/api/plans/${PLAN_ID}`,
        `/api/plans/${PLAN_ID}/actions`,
        `/api/plans/${PLAN_ID}/facets`,
        `/api/plans/${PLAN_ID}/groups`,
      ]),
    );
    expect(screen.getByRole("button", { name: "Apply Plan" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Cancel Plan" })).toBeEnabled();

    await user.click(
      screen.getByRole("button", { name: "Next page of Plan actions" }),
    );
    expect(await screen.findByText(SECOND_ACTION_ID)).toBeVisible();
    expect(screen.queryByText(ACTION_ID)).not.toBeInTheDocument();
    expect(actionCursors).toContain(OPAQUE_ACTION_CURSOR);

    await user.click(groupButton);
    await waitFor(() =>
      expect(router.state.location.search).toContain("group_key=blocked"),
    );
  });

  it("renders the typed Plan not-found state instead of a generic failure", async () => {
    server.use(
      http.get(`*/api/plans/${PLAN_ID}`, () =>
        HttpResponse.json(planNotFound, { status: 404 }),
      ),
      ...auxiliaryDetailHandlers(),
    );
    renderPlanDetail(`/plans/${PLAN_ID}`);

    expect(
      await screen.findByRole("heading", { name: "Plan not found" }),
    ).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

function renderPlanList(initialEntry = "/plans") {
  return renderRoute(PlanList, "/plans", initialEntry);
}

function renderPlanDetail(initialEntry: string) {
  return renderRoute(PlanDetail, "/plans/:planId", initialEntry);
}

function renderPlanRoundTrip(initialEntry: string) {
  const router = createMemoryRouter(
    [
      { path: "/plans", Component: PlanList },
      { path: "/plans/:planId", Component: PlanDetail },
    ],
    { initialEntries: [initialEntry] },
  );
  const user = userEvent.setup();
  const view = render(
    <QueryClientProvider client={createQueryClient()}>
      <BootstrapContext value={normalBootstrap.data}>
        <RouterProvider router={router} />
      </BootstrapContext>
    </QueryClientProvider>,
  );
  return { ...view, router, user };
}

function renderRoute(
  Component: () => React.JSX.Element,
  path: string,
  initialEntry: string,
) {
  const router = createMemoryRouter([{ path, Component }], {
    initialEntries: [initialEntry],
  });
  const user = userEvent.setup();
  const view = render(
    <QueryClientProvider client={createQueryClient()}>
      <BootstrapContext value={normalBootstrap.data}>
        <RouterProvider router={router} />
      </BootstrapContext>
    </QueryClientProvider>,
  );
  return { ...view, router, user };
}

function detailHandlers(
  requestedPaths: Set<string>,
  actionCursors: Array<string | null>,
) {
  return [
    http.get(`*/api/plans/${PLAN_ID}`, ({ request }) => {
      const url = new URL(request.url);
      requestedPaths.add(url.pathname);
      return HttpResponse.json(readyPlanDetailEnvelope);
    }),
    http.get(`*/api/plans/${PLAN_ID}/actions`, ({ request }) => {
      const url = new URL(request.url);
      requestedPaths.add(url.pathname);
      actionCursors.push(url.searchParams.get("cursor"));
      return HttpResponse.json(
        url.searchParams.get("cursor") === OPAQUE_ACTION_CURSOR
          ? actionEnvelope([secondAction], null)
          : actionEnvelope([blockedAction], OPAQUE_ACTION_CURSOR),
      );
    }),
    http.get(`*/api/plans/${PLAN_ID}/facets`, ({ request }) => {
      requestedPaths.add(new URL(request.url).pathname);
      return HttpResponse.json(facetEnvelope);
    }),
    http.get(`*/api/plans/${PLAN_ID}/groups`, ({ request }) => {
      requestedPaths.add(new URL(request.url).pathname);
      return HttpResponse.json(groupEnvelope);
    }),
  ];
}

function auxiliaryDetailHandlers() {
  return detailHandlers(new Set<string>(), []).slice(1);
}

const emptyTypeCounts = {
  move: 0,
  refresh_metadata: 0,
  skip: 0,
} as const;

const mixedSummary = {
  counts: {
    applied: emptyTypeCounts,
    blocked: { ...emptyTypeCounts, move: 1 },
    failed: emptyTypeCounts,
    planned: { move: 1, refresh_metadata: 1, skip: 1 },
  },
  total: 4,
} satisfies PlanActionSummary;

const readyPlan = {
  created_at: "2026-07-13T00:00:00Z",
  library_id: LIBRARY_ID,
  plan_id: PLAN_ID,
  plan_type: "add",
  status: "ready",
  summary: mixedSummary,
} satisfies PlanSummary;

const readyPlanDetailEnvelope = {
  data: {
    active_operation_id: null,
    capabilities: {
      can_apply: true,
      can_cancel: true,
      can_recreate: true,
      disabled_reasons: [],
    },
    plan: {
      config_hash: "fixture-config-hash",
      created_at: readyPlan.created_at,
      library_id: readyPlan.library_id,
      library_root_at_plan: "/music/library",
      plan_id: readyPlan.plan_id,
      plan_type: readyPlan.plan_type,
      status: readyPlan.status,
    },
    summary: mixedSummary,
  },
  errors: [],
} satisfies ApiEnvelopePlanDetailData;

const secondPlan = {
  ...readyPlan,
  plan_id: SECOND_PLAN_ID,
  plan_type: "refresh",
} satisfies PlanSummary;

const blockedAction = {
  action_id: ACTION_ID,
  action_type: "move",
  artist_name_diagnostics: null,
  content_hash_at_plan: "content",
  library_id: LIBRARY_ID,
  metadata_hash_at_plan: "metadata",
  plan_id: PLAN_ID,
  reason: "target_exists",
  sort_order: 1,
  source_path: "Artist/Album/old.flac",
  status: "blocked",
  target_path: "Artist/Album/01 Title.flac",
  track_id: null,
} satisfies PlanActionResource;

const secondAction = {
  ...blockedAction,
  action_id: SECOND_ACTION_ID,
  action_type: "refresh_metadata",
  reason: null,
  sort_order: 2,
  status: "planned",
} satisfies PlanActionResource;

const facetEnvelope = {
  data: {
    facets: {
      action_type: [{ count: 1, value: "move" }],
      reason: [{ count: 1, value: "target_exists" }],
      status: [{ count: 1, value: "blocked" }],
    },
    target_collisions: 1,
    total: 1,
  },
  errors: [],
} satisfies ApiEnvelopePlanActionFacetsData;

const groupEnvelope = {
  data: {
    group_by: "status",
    items: [
      {
        blocked_count: 1,
        count: 1,
        key: "blocked",
        label: "Blocked actions",
        top_reason: "target_exists",
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopePlanActionGroupsData;

const storageFailure = {
  data: null,
  errors: [
    {
      code: "storage_unavailable",
      message: "Plan storage is unavailable.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;

const planNotFound = {
  data: null,
  errors: [
    {
      code: "plan_not_found",
      field: "path.plan_id",
      message: "Plan was not found.",
      retryable: false,
    },
  ],
} satisfies ApiFailureEnvelope;

function planListEnvelope(items: PlanSummary[], nextCursor: string | null) {
  return {
    data: {
      items,
      page: { limit: 100, next_cursor: nextCursor, total: 2 },
    },
    errors: [],
  } satisfies ApiEnvelopePaginatedDataPlanSummary;
}

function actionEnvelope(
  items: PlanActionResource[],
  nextCursor: string | null,
) {
  return {
    data: {
      items,
      page: { limit: 100, next_cursor: nextCursor, total: 2 },
    },
    errors: [],
  } satisfies ApiEnvelopePaginatedDataPlanActionResource;
}
