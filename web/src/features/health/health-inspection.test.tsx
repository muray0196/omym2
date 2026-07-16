/**
 * Summary: Tests persisted Health freshness, group drill-down, and Check availability.
 * Why: Ensures inspection stays URL-addressable and Check never starts implicitly.
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
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { Component as HealthRoute } from "../../routes/health/route";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import { completedCheckOperation } from "../../test/fixtures/operations";
import { server } from "../../test/server";
import { healthGroupValueLabel, issueTypePresentation } from "./health-catalog";

const COMPANION_ASSET_ID = "018f6a4f-3c2d-7b8a-9abc-def012345713";

describe("Health inspection", () => {
  it("drills into an opaque server group without starting the available Check control", async () => {
    let drillDownSeen = false;
    let checkStarts = 0;
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
      http.post("*/api/check/run", () => {
        checkStarts += 1;
        return HttpResponse.error();
      }),
    );
    const { router } = renderRoute("/health?group_by=severity");

    expect(await screen.findByText(/no automatic repair/i)).toBeVisible();
    expect(
      screen.getAllByText("Pending FileEvent requires review").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Findings checked/i)).toBeVisible();
    expect(screen.getByText(COMPANION_ASSET_ID)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Warnings/i }));

    await waitFor(() => expect(drillDownSeen).toBe(true));
    expect(router.state.location.search).toContain("group_key=warning");
    expect(screen.getByRole("button", { name: /run check/i })).toBeEnabled();
    expect(checkStarts).toBe(0);
  });

  it("maps catalog-backed and server-labeled group values", () => {
    expect(
      healthGroupValueLabel(
        "issue_type",
        "pending_file_event_exists",
        "Server label",
      ),
    ).toBe("Pending FileEvent requires review");
    expect(healthGroupValueLabel("severity", "warning", "Warnings")).toBe(
      "Warnings",
    );
    expect(
      healthGroupValueLabel("suggested_command", "history", "omym2 history"),
    ).toBe("omym2 history");
  });

  it("maps every known CheckIssue type with full presentation data", () => {
    for (const [value, tone] of [
      ["db_file_missing", "danger"],
      ["unmanaged_file_exists", "warning"],
      ["content_hash_changed", "danger"],
      ["metadata_hash_changed", "warning"],
      ["current_path_differs_from_canonical_path", "warning"],
      ["companion_file_missing", "danger"],
      ["companion_content_hash_changed", "danger"],
      ["companion_current_path_differs_from_canonical_path", "warning"],
      ["companion_owner_missing", "danger"],
      ["unmanaged_companion_exists", "warning"],
      ["failed_companion_source_exists", "danger"],
      ["unprocessed_file_missing", "danger"],
      ["unprocessed_content_hash_changed", "danger"],
      ["duplicate_candidate", "warning"],
      ["plan_source_changed", "warning"],
      ["pending_file_event_exists", "warning"],
      ["library_unregistered", "warning"],
      ["library_stale", "warning"],
      ["library_blocked", "warning"],
    ] as const) {
      const presentation = issueTypePresentation(value);
      expect(presentation.icon).toBe("warning");
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).toBe(tone);
    }
  });

  it("routes broken unprocessed-file evidence to History review", async () => {
    server.use(
      http.get("*/api/check", () => HttpResponse.json(unprocessedCheckIssues)),
      http.get("*/api/check/facets", () =>
        HttpResponse.json(unprocessedCheckFacets),
      ),
      http.get("*/api/check/groups", () =>
        HttpResponse.json(unprocessedCheckGroups),
      ),
    );
    renderRoute("/health?group_by=suggested_command");

    expect(
      await screen.findByText("Unprocessed file is missing"),
    ).toBeVisible();
    expect(await screen.findByText("omym2 history")).toBeVisible();
    expect(screen.getByText("History review required")).toBeVisible();
    expect(
      screen.getByText(/no automatic refresh or Add repair is safe/i),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Open History" })).toHaveAttribute(
      "href",
      "/history",
    );
  });

  it("bounds both Health collections and resets them for a changed filter", async () => {
    const issueCursors: Array<string | null> = [];
    const groupCursors: Array<string | null> = [];
    server.use(
      http.get("*/api/check", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        issueCursors.push(cursor);
        return HttpResponse.json(
          cursor === null ? firstCheckIssuePage : secondCheckIssuePage,
        );
      }),
      http.get("*/api/check/facets", () => HttpResponse.json(checkFacets)),
      http.get("*/api/check/groups", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        groupCursors.push(cursor);
        return HttpResponse.json(
          cursor === null ? firstCheckGroupPage : secondCheckGroupPage,
        );
      }),
    );
    const user = userEvent.setup();
    renderRoute("/health");

    expect(await screen.findByText("First finding detail")).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: /Pending FileEvent requires review/,
      }),
    ).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Next page of Health groups" }),
    );
    expect(
      await screen.findByRole("button", { name: /Managed file is missing/ }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", {
        name: /Pending FileEvent requires review/,
      }),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Next page of Findings" }),
    );
    expect(await screen.findByText("Second finding detail")).toBeVisible();
    expect(screen.queryByText("First finding detail")).not.toBeInTheDocument();
    expect(issueCursors).toContain(HEALTH_CURSOR);
    expect(groupCursors).toContain(HEALTH_CURSOR);

    await user.selectOptions(
      screen.getByRole("combobox", { name: "Issue type" }),
      "pending_file_event_exists",
    );

    expect(await screen.findByText("First finding detail")).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: /Pending FileEvent requires review/,
      }),
    ).toBeVisible();
    expect(screen.queryByText("Second finding detail")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Managed file is missing/ }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Page 1 of 2")).toHaveLength(2);
  });

  it("runs Check with safe headers and refreshes persisted findings", async () => {
    let issueReads = 0;
    let csrfHeader: string | null = null;
    let idempotencyHeader: string | null = null;
    server.use(
      http.get("*/api/check", () => {
        issueReads += 1;
        return HttpResponse.json(checkIssues);
      }),
      http.get("*/api/check/facets", () => HttpResponse.json(checkFacets)),
      http.get("*/api/check/groups", () => HttpResponse.json(checkGroups)),
      http.post("*/api/check/run", ({ request }) => {
        csrfHeader = request.headers.get("X-OMYM2-CSRF-Token");
        idempotencyHeader = request.headers.get("Idempotency-Key");
        return HttpResponse.json(completedCheckOperation);
      }),
    );
    renderRoute("/health");

    await userEvent.click(
      await screen.findByRole("button", { name: /^run check$/i }),
    );

    expect(
      await screen.findByText(/Saved 2 findings across 1 Check runs/i),
    ).toBeVisible();
    await waitFor(() => expect(issueReads).toBeGreaterThan(1));
    expect(csrfHeader).toBe(normalBootstrap.data.csrf_token);
    expect(idempotencyHeader).toMatch(/^[0-9a-f-]{36}$/);
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
        <BootstrapContext value={normalBootstrap.data}>
          <RouterProvider router={router} />
        </BootstrapContext>
      </QueryClientProvider>,
    ),
  };
}

const checkIssues = {
  data: {
    checked_at: "2026-07-13T00:00:00Z",
    items: [
      {
        companion_asset_id: COMPANION_ASSET_ID,
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

const unprocessedCheckIssues = {
  data: {
    checked_at: "2026-07-16T00:00:00Z",
    items: [
      {
        companion_asset_id: null,
        issue_type: "unprocessed_file_missing",
        library_id: "018f6a4f-3c2d-7b8a-9abc-def012345711",
        path: "/incoming/unprocessed/notes.txt",
        track_id: null,
        plan_id: null,
        detail: "Recorded unprocessed-file target is missing.",
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssuesData;
const unprocessedCheckFacets = {
  data: {
    checked_at: "2026-07-16T00:00:00Z",
    facets: { issue_type: [{ value: "unprocessed_file_missing", count: 1 }] },
    total: 1,
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueFacetsData;
const unprocessedCheckGroups = {
  data: {
    group_by: "suggested_command",
    items: [
      {
        key: "history",
        label: "omym2 history",
        count: 1,
        common_path_root: "/",
      },
    ],
    page: { limit: 100, next_cursor: null, total: 1 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueGroupsData;

const HEALTH_CURSOR = "opaque-health-cursor";
const firstCheckIssuePage = {
  data: {
    checked_at: "2026-07-13T00:00:00Z",
    items: [
      {
        companion_asset_id: null,
        issue_type: "pending_file_event_exists",
        library_id: "018f6a4f-3c2d-7b8a-9abc-def012345711",
        path: "Artist/First.flac",
        track_id: null,
        plan_id: "018f6a4f-3c2d-7b8a-9abc-def012345712",
        detail: "First finding detail",
      },
    ],
    page: { limit: 1, next_cursor: HEALTH_CURSOR, total: 2 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssuesData;
const secondCheckIssuePage = {
  data: {
    checked_at: "2026-07-13T00:00:00Z",
    items: [
      {
        companion_asset_id: null,
        issue_type: "db_file_missing",
        library_id: "018f6a4f-3c2d-7b8a-9abc-def012345711",
        path: "Artist/Second.flac",
        track_id: null,
        plan_id: null,
        detail: "Second finding detail",
      },
    ],
    page: { limit: 1, next_cursor: null, total: 2 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssuesData;
const firstCheckGroupPage = {
  data: {
    group_by: "issue_type",
    items: [
      {
        key: "pending_file_event_exists",
        label: "First finding group",
        count: 1,
        common_path_root: null,
      },
    ],
    page: { limit: 1, next_cursor: HEALTH_CURSOR, total: 2 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueGroupsData;
const secondCheckGroupPage = {
  data: {
    group_by: "issue_type",
    items: [
      {
        key: "db_file_missing",
        label: "Second finding group",
        count: 1,
        common_path_root: null,
      },
    ],
    page: { limit: 1, next_cursor: null, total: 2 },
  },
  errors: [],
} satisfies ApiEnvelopeCheckIssueGroupsData;
