/**
 * Summary: Captures the required desktop visual baseline matrix.
 * Why: Makes layout, state, zoom, and reduced-motion regressions executable in Chromium.
 */
import type { Page, Route } from "@playwright/test";

import type {
  ApiEnvelopePaginatedDataPlanSummary,
  ApiEnvelopePaginatedDataTrackResource,
  ApiEnvelopeTrackFacetsData,
  ApiEnvelopeTrackGroupsData,
  ApiFailureEnvelope,
  TrackResource,
} from "../src/api/generated";
import { normalBootstrap } from "../src/test/fixtures/bootstrap";
import { planListFirstPage } from "../src/test/fixtures/plans";
import { settingsEnvelope } from "../src/test/fixtures/settings";
import {
  applyDesktopZoom,
  DESKTOP_ZOOM_EXPECTED_METRICS,
  readDesktopZoomMetrics,
} from "./desktop-zoom";
import { expect, test } from "./playwright-fixtures";

const WIDE_DESKTOP_VIEWPORT = { height: 800, width: 1280 } as const;
const COMPACT_DESKTOP_VIEWPORT = { height: 768, width: 1024 } as const;
const LARGE_RESULT_COUNT = 1_000_000;
const LONG_PATH_SEGMENT_COUNT = 6;
const LONG_PATH = `/music/${"long-directory-name/".repeat(LONG_PATH_SEGMENT_COUNT)}track.flac`;
const BOOTSTRAP_REQUEST = /\/api\/bootstrap$/;
const PLAN_LIST_REQUEST = /\/api\/plans(?:\?.*)?$/;
const SETTINGS_REQUEST = /\/api\/settings$/;
const TRACK_LIST_REQUEST = /\/api\/tracks(?:\?.*)?$/;
const TRACK_FACETS_REQUEST = /\/api\/tracks\/facets(?:\?.*)?$/;
const TRACK_GROUPS_REQUEST = /\/api\/tracks\/groups(?:\?.*)?$/;
const SCREENSHOT_OPTIONS = {
  animations: "disabled",
  fullPage: true,
} as const;
const VIEWPORT_SCREENSHOT_OPTIONS = {
  animations: "disabled",
} as const;
const LIBRARY_ID = "018f0000-0000-7000-8000-000000000001";
const LIBRARY_TRACKS = [
  libraryTrack({
    id: "018f0000-0000-7000-8000-000000000101",
    title: "So What",
    trackNumber: 1,
  }),
  libraryTrack({
    id: "018f0000-0000-7000-8000-000000000102",
    title: "Freddie Freeloader",
    trackNumber: 2,
  }),
  libraryTrack({
    album: "Blue Train",
    artist: "John Coltrane",
    id: "018f0000-0000-7000-8000-000000000103",
    title: "Moment's Notice",
    trackNumber: 3,
    year: 1958,
  }),
] satisfies TrackResource[];

test.beforeEach(async ({ page }) => {
  await page.route(BOOTSTRAP_REQUEST, (route) =>
    fulfillJson(route, normalBootstrap),
  );
});

test("matches the wide supported desktop layout", async ({ page }) => {
  await page.setViewportSize(WIDE_DESKTOP_VIEWPORT);
  await fulfillPlanList(page, planListFirstPage);
  await openLoadedPlans(page);

  await expect(page).toHaveScreenshot("plans-wide.png", SCREENSHOT_OPTIONS);
});

test("matches the compact supported desktop layout", async ({ page }) => {
  await page.setViewportSize(COMPACT_DESKTOP_VIEWPORT);
  await fulfillPlanList(page, planListFirstPage);
  await openLoadedPlans(page);

  await expect(page).toHaveScreenshot("plans-compact.png", SCREENSHOT_OPTIONS);
});

test("matches the tracks-first Library layout", async ({ page }) => {
  await page.setViewportSize(WIDE_DESKTOP_VIEWPORT);
  await fulfillLibrary(page);
  await openLoadedLibrary(page);

  await expect(page).toHaveScreenshot(
    "library-tracks-wide.png",
    SCREENSHOT_OPTIONS,
  );
});

test("matches the compact tracks-first Library layout", async ({ page }) => {
  await page.setViewportSize(COMPACT_DESKTOP_VIEWPORT);
  await fulfillLibrary(page);
  await openLoadedLibrary(page);

  await expect(page).toHaveScreenshot(
    "library-tracks-compact.png",
    SCREENSHOT_OPTIONS,
  );
});

test("matches the 200% zoom Library reflow", async ({ page }) => {
  await fulfillLibrary(page);
  await openLoadedLibrary(page);
  const zoomSession = await applyDesktopZoom(page);
  try {
    await expect
      .poll(() => readDesktopZoomMetrics(page))
      .toEqual(DESKTOP_ZOOM_EXPECTED_METRICS);
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth >
            document.documentElement.clientWidth,
        ),
      )
      .toBe(false);
    await page
      .getByRole("heading", { name: "Tracks" })
      .scrollIntoViewIfNeeded();

    const screenshot = await zoomSession.send("Page.captureScreenshot", {
      captureBeyondViewport: false,
      format: "png",
      fromSurface: true,
    });
    expect(Buffer.from(screenshot.data, "base64")).toMatchSnapshot(
      "library-tracks-200-percent-zoom.png",
    );
  } finally {
    await zoomSession.detach();
  }
});

test("keeps the Library view toggle anchored while switching views", async ({
  page,
}) => {
  await fulfillLibrary(page);
  for (const viewport of [WIDE_DESKTOP_VIEWPORT, COMPACT_DESKTOP_VIEWPORT]) {
    await page.setViewportSize(viewport);
    await openLoadedLibrary(page);
    const toggle = page.getByRole("group", { name: "Library view" });
    const tracksPosition = await toggle.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return { x: bounds.x, y: bounds.y };
    });

    await page.getByRole("button", { name: "Browse groups" }).click();
    await expect(
      page.getByRole("heading", { name: "Browse Library" }),
    ).toBeVisible();
    const groupsPosition = await toggle.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return { x: bounds.x, y: bounds.y };
    });

    expect(groupsPosition).toEqual(tracksPosition);
  }
});

test("matches the alternate Library group browser", async ({ page }) => {
  await page.setViewportSize(WIDE_DESKTOP_VIEWPORT);
  await fulfillLibrary(page);
  await page.goto("/library?view=groups");
  await expect(
    page.getByRole("heading", { name: "Browse Library" }),
  ).toBeVisible();
  await waitForStableShell(page);

  await expect(page).toHaveScreenshot(
    "library-groups-wide.png",
    SCREENSHOT_OPTIONS,
  );
});

test("matches the deliberate loading state", async ({ page }) => {
  let releaseRequest: () => void = () => undefined;
  const requestHeld = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  await page.route(PLAN_LIST_REQUEST, async (route) => {
    await requestHeld;
    await fulfillJson(route, planListFirstPage);
  });
  await page.goto("/plans");
  await expect(page.getByText("Loading Plans…", { exact: true })).toBeVisible();
  await waitForStableShell(page);

  try {
    await expect(page).toHaveScreenshot(
      "plans-loading.png",
      SCREENSHOT_OPTIONS,
    );
  } finally {
    releaseRequest();
  }
});

test("matches the empty result state", async ({ page }) => {
  await fulfillPlanList(page, {
    data: {
      items: [],
      page: { limit: 100, next_cursor: null, total: 0 },
    },
    errors: [],
  });
  await page.goto("/plans");
  await expect(
    page.getByRole("heading", { name: "No Plans have been recorded" }),
  ).toBeVisible();
  await waitForStableShell(page);

  await expect(page).toHaveScreenshot("plans-empty.png", SCREENSHOT_OPTIONS);
});

test("matches the typed error state", async ({ page }) => {
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
  await page.route(PLAN_LIST_REQUEST, (route) =>
    fulfillJson(route, failure, 500),
  );
  await page.goto("/plans");
  await expect(page.getByRole("alert")).toContainText(
    "Plan storage is temporarily unavailable.",
  );
  await waitForStableShell(page);

  await expect(page).toHaveScreenshot("plans-error.png", SCREENSHOT_OPTIONS);
});

test("matches a long path without horizontal page overflow", async ({
  page,
}) => {
  await page.route(SETTINGS_REQUEST, (route) =>
    fulfillJson(route, settingsEnvelope),
  );
  await page.goto("/settings");
  const libraryPath = page.getByRole("textbox", { name: "Library path" });
  await libraryPath.fill(LONG_PATH);
  await expect(libraryPath).toHaveValue(LONG_PATH);
  await libraryPath.blur();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
  await waitForStableShell(page);

  await expect(page).toHaveScreenshot(
    "settings-long-path.png",
    VIEWPORT_SCREENSHOT_OPTIONS,
  );
});

test("matches a large result count", async ({ page }) => {
  const largeCountPage = {
    ...planListFirstPage,
    data: {
      ...planListFirstPage.data,
      page: { ...planListFirstPage.data.page, total: LARGE_RESULT_COUNT },
    },
  } satisfies ApiEnvelopePaginatedDataPlanSummary;
  await fulfillPlanList(page, largeCountPage);
  await openLoadedPlans(page);
  await expect(
    page.getByText(
      `${LARGE_RESULT_COUNT.toLocaleString("en-US")} matching Plans`,
    ),
  ).toBeVisible();

  await expect(page).toHaveScreenshot(
    "plans-large-count.png",
    SCREENSHOT_OPTIONS,
  );
});

test("matches the 200% desktop reflow state", async ({ page }) => {
  await fulfillPlanList(page, planListFirstPage);
  await openLoadedPlans(page);
  const zoomSession = await applyDesktopZoom(page);
  try {
    await expect
      .poll(() => readDesktopZoomMetrics(page))
      .toEqual(DESKTOP_ZOOM_EXPECTED_METRICS);

    const screenshot = await zoomSession.send("Page.captureScreenshot", {
      captureBeyondViewport: false,
      format: "png",
      fromSurface: true,
    });
    expect(Buffer.from(screenshot.data, "base64")).toMatchSnapshot(
      "plans-200-percent-zoom.png",
    );
  } finally {
    await zoomSession.detach();
  }
});

test("matches the reduced-motion state", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fulfillPlanList(page, planListFirstPage);
  await openLoadedPlans(page);
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Keyboard shortcuts" }).click();
  await expect(
    page.getByRole("dialog", { name: "Keyboard shortcuts" }),
  ).toBeVisible();

  await expect(page).toHaveScreenshot(
    "shortcuts-reduced-motion.png",
    SCREENSHOT_OPTIONS,
  );
});

async function fulfillPlanList(
  page: Page,
  envelope: ApiEnvelopePaginatedDataPlanSummary,
) {
  await page.route(PLAN_LIST_REQUEST, (route) => fulfillJson(route, envelope));
}

async function fulfillLibrary(page: Page) {
  const tracks = {
    data: {
      items: LIBRARY_TRACKS,
      page: { limit: 100, next_cursor: null, total: LIBRARY_TRACKS.length },
    },
    errors: [],
  } satisfies ApiEnvelopePaginatedDataTrackResource;
  const facets = {
    data: {
      facets: { status: [{ count: LIBRARY_TRACKS.length, value: "active" }] },
      total: LIBRARY_TRACKS.length,
    },
    errors: [],
  } satisfies ApiEnvelopeTrackFacetsData;
  const groups = {
    data: {
      group_by: "artist",
      items: [
        { count: 2, key: '["Miles Davis"]', label: "Miles Davis" },
        { count: 1, key: '["John Coltrane"]', label: "John Coltrane" },
      ],
      page: { limit: 100, next_cursor: null, total: 2 },
    },
    errors: [],
  } satisfies ApiEnvelopeTrackGroupsData;
  await page.route(TRACK_LIST_REQUEST, (route) => fulfillJson(route, tracks));
  await page.route(TRACK_FACETS_REQUEST, (route) => fulfillJson(route, facets));
  await page.route(TRACK_GROUPS_REQUEST, (route) => fulfillJson(route, groups));
}

async function fulfillJson(route: Route, body: object, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  });
}

async function openLoadedPlans(page: Page) {
  await page.goto("/plans");
  await expect(
    page.getByRole("heading", { level: 1, name: "Plans" }),
  ).toBeVisible();
  await expect(page.getByText("Loading Plans…")).not.toBeVisible();
  await waitForStableShell(page);
}

async function openLoadedLibrary(page: Page) {
  await page.goto("/library");
  await expect(page.getByRole("heading", { name: "Tracks" })).toBeVisible();
  await expect(page.getByRole("link", { name: /So What/ })).toBeVisible();
  await waitForStableShell(page);
}

function libraryTrack({
  album = "Kind of Blue",
  artist = "Miles Davis",
  id,
  title,
  trackNumber,
  year = 1959,
}: {
  album?: string;
  artist?: string;
  id: string;
  title: string;
  trackNumber: number;
  year?: number;
}): TrackResource {
  const path = `${artist}/${year}_${album}/1-${trackNumber}_${title}.flac`;
  return {
    canonical_path: path,
    content_hash: `content-${id}`,
    current_path: path,
    first_seen_at: "2026-07-01T00:00:00Z",
    last_seen_at: "2026-07-14T00:00:00Z",
    library_id: LIBRARY_ID,
    metadata: {
      album,
      album_artist: artist,
      artist,
      disc_number: 1,
      disc_total: 1,
      genre: "Jazz",
      title,
      track_number: trackNumber,
      track_total: 5,
      year,
    },
    metadata_hash: `metadata-${id}`,
    mtime: "2026-07-14T00:00:00Z",
    size: 1_234_567,
    status: "active",
    track_id: id,
    updated_at: "2026-07-14T00:00:00Z",
  };
}

async function waitForStableShell(page: Page) {
  await expect(page.locator('[data-bootstrap-state="normal"]')).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
