/**
 * Summary: Owns the MSW server used by frontend tests.
 * Why: Gives generated API handlers one strict shared interception boundary.
 */
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { ApiEnvelopeLibrariesData } from "../api/generated";
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
  readyPlanDetail,
  readyPlanFacets,
  readyPlanGroupsFirstPage,
  readyPlanGroupsSecondPage,
} from "./fixtures/plans";
import {
  previewEnvelope,
  reviewedSettingsEnvelope,
  savedSettingsEnvelope,
  settingsEnvelope,
} from "./fixtures/settings";

const libraries = {
  data: {
    items: normalBootstrap.data?.active_library
      ? [normalBootstrap.data.active_library]
      : [],
  },
  errors: [],
} satisfies ApiEnvelopeLibrariesData;

export const server = setupServer(
  http.get("*/api/bootstrap", () => HttpResponse.json(normalBootstrap)),
  http.get("*/api/libraries", () => HttpResponse.json(libraries)),
  http.get("*/api/settings", () => HttpResponse.json(settingsEnvelope)),
  http.post("*/api/settings/validate", () =>
    HttpResponse.json(reviewedSettingsEnvelope),
  ),
  http.post("*/api/settings/preview", () => HttpResponse.json(previewEnvelope)),
  http.put("*/api/settings", () => HttpResponse.json(savedSettingsEnvelope)),
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
  http.get("*/api/plans/:planId", () => HttpResponse.json(readyPlanDetail)),
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
