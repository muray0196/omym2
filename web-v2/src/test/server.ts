/**
 * Summary: Owns the clean-room MSW server used by frontend tests.
 * Why: Gives generated API handlers one strict shared interception boundary.
 */
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { normalBootstrap } from "./fixtures/bootstrap";
import {
  BLOCKED_PLAN_ID,
  OPAQUE_ACTION_CURSOR,
  OPAQUE_GROUP_CURSOR,
  OPAQUE_PLAN_CURSOR,
  READY_PLAN_ID,
  emptyPlanPage,
  exactBlockedPlanPage,
  exactReadyPlanPage,
  planListFirstPage,
  planListSecondPage,
  readyPlanActionsFirstPage,
  readyPlanActionsSecondPage,
  readyPlanFacets,
  readyPlanGroupsFirstPage,
  readyPlanGroupsSecondPage,
} from "./fixtures/plans";

export const server = setupServer(
  http.get("*/api/bootstrap", () => HttpResponse.json(normalBootstrap)),
  http.get("*/api/plans", ({ request }) => {
    const parameters = new URL(request.url).searchParams;
    const query = parameters.get("query");
    const cursor = parameters.get("cursor");

    if (query === READY_PLAN_ID) {
      return HttpResponse.json(exactReadyPlanPage);
    }
    if (query === BLOCKED_PLAN_ID) {
      return HttpResponse.json(exactBlockedPlanPage);
    }
    if (query !== null && query.startsWith("019")) {
      return HttpResponse.json(emptyPlanPage);
    }
    if (cursor === OPAQUE_PLAN_CURSOR) {
      return HttpResponse.json(planListSecondPage);
    }
    return HttpResponse.json(planListFirstPage);
  }),
  http.get("*/api/plans/:planId/actions", ({ request }) => {
    const cursor = new URL(request.url).searchParams.get("cursor");
    return HttpResponse.json(
      cursor === OPAQUE_ACTION_CURSOR
        ? readyPlanActionsSecondPage
        : readyPlanActionsFirstPage,
    );
  }),
  http.get("*/api/plans/:planId/facets", () =>
    HttpResponse.json(readyPlanFacets),
  ),
  http.get("*/api/plans/:planId/groups", ({ request }) => {
    const cursor = new URL(request.url).searchParams.get("cursor");
    return HttpResponse.json(
      cursor === OPAQUE_GROUP_CURSOR
        ? readyPlanGroupsSecondPage
        : readyPlanGroupsFirstPage,
    );
  }),
);
