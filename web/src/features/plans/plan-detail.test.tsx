/**
 * Summary: Verifies exact Plan review, capability controls, Apply polling, and safe Cancel.
 * Why: Prevents execution from inferring permission or retrying unsafe mutations.
 */
import { http, HttpResponse } from "msw";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopePlanDetailData,
  ApiFailureEnvelope,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { server } from "../../test/server";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import {
  OPERATION_ID,
  completedRunOperation,
  queuedOperation,
} from "../../test/fixtures/operations";
import {
  BLOCKED_PLAN_ID,
  OPAQUE_ACTION_CURSOR,
  READY_PLAN_ID,
  blockedOnlyPlanDetail,
  cancelledPlanDetail,
  readyPlanActionsFirstPage,
  readyPlanActionsSecondPage,
  readyPlanDetail,
  readyPlanFacets,
  readyPlanGroupsFirstPage,
} from "../../test/fixtures/plans";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { PlanDetail } from "./plan-detail";

describe("PlanDetail", () => {
  it("loads exact typed detail and independent actions, facets, and groups", async () => {
    const actionCursors: Array<string | null> = [];
    let detailReads = 0;
    server.use(
      http.get("*/api/plans/:planId", () => {
        detailReads += 1;
        return HttpResponse.json(readyPlanDetail);
      }),
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
    const loadingHeading = screen.getByRole("heading", {
      name: "Plan detail",
    });
    const backLink = screen.getByRole("link", { name: "Back to Plans" });
    expect(loadingHeading).toHaveFocus();
    backLink.focus();
    await screen.findByRole("heading", { name: "Recorded action summary" });
    expect(screen.getByRole("heading", { name: "Plan detail" })).toBe(
      loadingHeading,
    );
    expect(backLink).toHaveFocus();
    await screen.findByText("Action facets");
    await screen.findByText("Action groups");
    expect(detailReads).toBe(1);
    expect(screen.getByRole("button", { name: "Apply Plan" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Cancel Plan" })).toBeEnabled();
    expect(
      screen.getByRole("button", {
        name: "Create a new Plan from the current state",
      }),
    ).toBeEnabled();
    expect(
      screen.getByText(/blocked action remains unresolved/i),
    ).toBeVisible();

    expect(
      screen.getByText("01912345-6789-7abc-8def-012345678911"),
    ).toBeVisible();
    const artistNamingHeading = screen.getByRole("heading", {
      name: "Artist naming",
    });
    const artistNaming = within(artistNamingHeading.parentElement!);
    expect(artistNaming.getByText("Artist")).toBeVisible();
    expect(artistNaming.getByText("Album artist")).toBeVisible();
    expect(artistNaming.getByText("Hikaru Utada")).toBeVisible();
    expect(artistNaming.getByText("New MusicBrainz result")).toBeVisible();
    expect(artistNaming.getByText("Original metadata")).toBeVisible();
    expect(artistNaming.getByText("None")).toBeVisible();
    expect(artistNaming.getByText("Ambiguous match")).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Next page of Plan actions" }),
    );
    await waitFor(() => expect(actionCursors).toContain(OPAQUE_ACTION_CURSOR));
    expect(
      screen.queryByText("01912345-6789-7abc-8def-012345678911"),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: /^Unknown status: fixture-group-planned/,
      }),
    );
    await waitFor(() => {
      const parameters = new URLSearchParams(router.state.location.search);
      expect(parameters.get("group_key")).toBe("fixture-group-planned");
    });
  });

  it("renders null names and preserves unknown diagnostic catalog values", async () => {
    const [action] = readyPlanActionsFirstPage.data.items;
    if (action === undefined) {
      throw new Error("The Plan action fixture must not be empty.");
    }
    server.use(
      http.get("*/api/plans/:planId/actions", () =>
        HttpResponse.json({
          data: {
            items: [
              {
                ...action,
                artist_name_diagnostics: {
                  artist: {
                    issue: "future_issue",
                    provenance: "future_provenance",
                    resolved_name: null,
                    source_name: null,
                  },
                  album_artist: {
                    issue: null,
                    provenance: "original",
                    resolved_name: "Album Artist",
                    source_name: "Album Artist",
                  },
                },
              },
            ],
            page: { limit: 100, next_cursor: null, total: 1 },
          },
          errors: [],
        }),
      ),
    );
    renderPlanDetail();

    const artistNamingHeading = await screen.findByRole("heading", {
      name: "Artist naming",
    });
    const artistNaming = within(artistNamingHeading.parentElement!);
    expect(artistNaming.getAllByText("—")).toHaveLength(2);
    expect(
      artistNaming.getByText(/Unknown provenance: future_provenance/),
    ).toBeVisible();
    expect(artistNaming.getByText(/Unknown issue: future_issue/)).toBeVisible();
  });

  it("starts Apply once, polls durable progress, and opens the completed Run in History", async () => {
    const applyHeaders: Headers[] = [];
    let operationReads = 0;
    server.use(
      http.get("*/api/plans/:planId", () => HttpResponse.json(readyPlanDetail)),
      http.post("*/api/plans/:planId/apply", ({ request }) => {
        applyHeaders.push(request.headers);
        return HttpResponse.json(queuedOperation("apply_plan"), {
          status: 202,
        });
      }),
      http.get("*/api/operations/:operationId", () => {
        operationReads += 1;
        return HttpResponse.json(completedRunOperation);
      }),
    );
    const { user } = renderPlanDetail();

    await user.click(await screen.findByRole("button", { name: "Apply Plan" }));

    expect(
      await screen.findByRole("heading", { name: "Completed Run" }),
    ).toBeVisible();
    expect(operationReads).toBe(1);
    expect(applyHeaders[0]?.get("X-OMYM2-CSRF-Token")).toBe(
      normalBootstrap.data.csrf_token,
    );
    expect(applyHeaders[0]?.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("keeps backend-permitted Apply enabled for a blocked-only zero-mutation Plan", async () => {
    server.use(
      http.get("*/api/plans/:planId", () =>
        HttpResponse.json(blockedOnlyPlanDetail),
      ),
    );
    renderPlanDetail(`/plans/${BLOCKED_PLAN_ID}`);

    expect(
      await screen.findByRole("button", { name: "Apply Plan" }),
    ).toBeEnabled();
    expect(
      screen.getByText(/this Plan will not mutate a library file/i),
    ).toBeVisible();
  });

  it("refreshes Bootstrap once for safe Cancel and focuses the updated controls", async () => {
    const refreshedToken = "refreshed-csrf-token";
    const sentTokens: Array<string | null> = [];
    let detailEnvelope: ApiEnvelopePlanDetailData = readyPlanDetail;
    server.use(
      http.get("*/api/plans/:planId", () => HttpResponse.json(detailEnvelope)),
      http.get("*/api/bootstrap", () =>
        HttpResponse.json({
          ...normalBootstrap,
          data: { ...normalBootstrap.data, csrf_token: refreshedToken },
        }),
      ),
      http.post("*/api/plans/:planId/cancel", ({ request }) => {
        sentTokens.push(request.headers.get("X-OMYM2-CSRF-Token"));
        if (sentTokens.length === 1) {
          return HttpResponse.json(csrfFailure, { status: 403 });
        }
        detailEnvelope = cancelledPlanDetail;
        return HttpResponse.json(cancelledPlanDetail);
      }),
    );
    const { user } = renderPlanDetail();

    await user.click(
      await screen.findByRole("button", { name: "Cancel Plan" }),
    );
    const confirmation = await screen.findByRole("dialog", {
      name: "Cancel this Plan?",
    });
    expect(
      within(confirmation).getByRole("button", { name: "Keep Plan" }),
    ).toHaveFocus();
    expect(sentTokens).toHaveLength(0);
    await user.click(
      within(confirmation).getByRole("button", { name: "Keep Plan" }),
    );
    await waitFor(() => expect(confirmation).not.toBeVisible());
    expect(screen.getByRole("button", { name: "Cancel Plan" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Cancel Plan" }));
    await user.click(
      within(
        await screen.findByRole("dialog", { name: "Cancel this Plan?" }),
      ).getByRole("button", { name: "Cancel this Plan" }),
    );

    expect(
      await screen.findByText("Plan cancelled. Execution controls updated."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Cancelled")).toBeInTheDocument(),
    );
    expect(sentTokens).toEqual([
      normalBootstrap.data.csrf_token,
      refreshedToken,
    ]);
    expect(
      screen
        .getByRole("heading", { name: "Plan execution" })
        .closest("section"),
    ).toHaveFocus();
  });

  it("does not retry a Cancel conflict and focuses its backend remediation", async () => {
    let attempts = 0;
    let bootstrapReads = 0;
    let detailEnvelope: ApiEnvelopePlanDetailData = readyPlanDetail;
    server.use(
      http.get("*/api/bootstrap", () => {
        bootstrapReads += 1;
        return HttpResponse.json(normalBootstrap);
      }),
      http.get("*/api/plans/:planId", () => HttpResponse.json(detailEnvelope)),
      http.post("*/api/plans/:planId/cancel", () => {
        attempts += 1;
        detailEnvelope = claimedPlanDetail;
        return HttpResponse.json(cancelConflict, { status: 409 });
      }),
    );
    const { user } = renderPlanDetail(`/plans/${READY_PLAN_ID}`, true);

    await waitFor(() => expect(bootstrapReads).toBe(1));

    await user.click(
      await screen.findByRole("button", { name: "Cancel Plan" }),
    );
    await user.click(
      within(
        await screen.findByRole("dialog", { name: "Cancel this Plan?" }),
      ).getByRole("button", { name: "Cancel this Plan" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveFocus();
    expect(alert).toHaveTextContent("The Plan was claimed by Apply.");
    expect(attempts).toBe(1);
    expect(
      screen.getByRole("link", { name: "Inspect current History" }),
    ).toHaveAttribute("href", "/history");
    await waitFor(() => {
      expect(screen.getByText("Applying")).toBeVisible();
      expect(screen.getByRole("button", { name: "Apply Plan" })).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Cancel Plan" }),
      ).toBeDisabled();
      expect(bootstrapReads).toBe(2);
    });
  });

  it("refetches backend capability state after an Apply race without retrying", async () => {
    let attempts = 0;
    let bootstrapReads = 0;
    let detailEnvelope: ApiEnvelopePlanDetailData = readyPlanDetail;
    server.use(
      http.get("*/api/bootstrap", () => {
        bootstrapReads += 1;
        return HttpResponse.json(normalBootstrap);
      }),
      http.get("*/api/plans/:planId", () => HttpResponse.json(detailEnvelope)),
      http.post("*/api/plans/:planId/apply", () => {
        attempts += 1;
        detailEnvelope = claimedPlanDetail;
        return HttpResponse.json(cancelConflict, { status: 409 });
      }),
    );
    const { user } = renderPlanDetail(`/plans/${READY_PLAN_ID}`, true);

    await waitFor(() => expect(bootstrapReads).toBe(1));
    await user.click(await screen.findByRole("button", { name: "Apply Plan" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveFocus();
    expect(alert).toHaveTextContent("The Plan was claimed by Apply.");
    expect(attempts).toBe(1);
    await waitFor(() => {
      expect(screen.getByText("Applying")).toBeVisible();
      expect(screen.getByRole("button", { name: "Apply Plan" })).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Cancel Plan" }),
      ).toBeDisabled();
      expect(bootstrapReads).toBe(2);
    });
  });

  it("keeps every denied control visible with backend recovery guidance", async () => {
    server.use(
      http.get("*/api/plans/:planId", () =>
        HttpResponse.json(disabledPlanDetail),
      ),
    );
    renderPlanDetail();

    expect(
      await screen.findByRole("button", { name: "Apply Plan" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel Plan" })).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Create a new Plan from the current state",
      }),
    ).toBeDisabled();
    expect(screen.getByText("Another Operation owns this Plan.")).toBeVisible();
    expect(screen.getByText("omym2 history")).toBeVisible();
    expect(
      screen.getAllByRole("link", { name: "View active Operation" })[0],
    ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);
    expect(
      screen.getByRole("link", { name: "Recover active Operation" }),
    ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);
  });

  it("renders an accessible not-found state from exact Plan lookup", async () => {
    const missingPlanId = "01912345-6789-7abc-8def-012345678999";
    server.use(
      http.get("*/api/plans/:planId", () =>
        HttpResponse.json(
          {
            data: null,
            errors: [
              {
                code: "plan_not_found",
                field: "path.plan_id",
                message: "Plan was not found.",
                retryable: false,
              },
            ],
          },
          { status: 404 },
        ),
      ),
    );
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

function renderPlanDetail(
  initialEntry = `/plans/${READY_PLAN_ID}`,
  observeBootstrap = false,
) {
  const router = createMemoryRouter(
    [
      { path: "/plans/:planId", Component: PlanDetail },
      {
        path: "/history/:runId",
        element: <RouteHeading>Completed Run</RouteHeading>,
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

const csrfFailure = {
  data: null,
  errors: [
    {
      code: "csrf_invalid",
      field: "header.X-OMYM2-CSRF-Token",
      message: "The CSRF token expired.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;

const cancelConflict = {
  data: null,
  errors: [
    {
      code: "plan_not_ready",
      field: "path.plan_id",
      message: "The Plan was claimed by Apply.",
      remediation: {
        label: "Inspect current History",
        route: "/history",
      },
      retryable: false,
    },
  ],
} satisfies ApiFailureEnvelope;

const disabledPlanDetail = {
  data: {
    ...readyPlanDetail.data,
    active_operation_id: OPERATION_ID,
    capabilities: {
      can_apply: false,
      can_cancel: false,
      can_recreate: false,
      disabled_reasons: [
        {
          code: "operation_in_progress",
          field: "capabilities.can_apply",
          message: "Another Operation owns this Plan.",
          remediation: {
            label: "View active Operation",
            route: `/api/operations/${OPERATION_ID}`,
          },
          retryable: true,
        },
        {
          code: "plan_not_ready",
          field: "capabilities.can_cancel",
          message: "The Plan cannot be cancelled now.",
          retryable: false,
        },
        {
          code: "plan_not_ready",
          field: "capabilities.can_recreate",
          message: "Inspect durable History before creating another Plan.",
          remediation: {
            command: "omym2 history",
            label: "Inspect History",
            route: "/history",
          },
          retryable: false,
        },
      ],
    },
  },
  errors: [],
} satisfies ApiEnvelopePlanDetailData;

const claimedPlanDetail = {
  ...disabledPlanDetail,
  data: {
    ...disabledPlanDetail.data,
    plan: { ...disabledPlanDetail.data.plan, status: "applying" },
  },
} satisfies ApiEnvelopePlanDetailData;
