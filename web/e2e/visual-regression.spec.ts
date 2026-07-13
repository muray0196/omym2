/**
 * Summary: Captures the required clean-room desktop visual baseline matrix.
 * Why: Makes M5 layout, state, zoom, and reduced-motion regressions executable in Chromium.
 */
import type { Page, Route } from "@playwright/test";

import type {
  ApiEnvelopePaginatedDataPlanSummary,
  ApiFailureEnvelope,
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
const SCREENSHOT_OPTIONS = {
  animations: "disabled",
  fullPage: true,
} as const;
const VIEWPORT_SCREENSHOT_OPTIONS = {
  animations: "disabled",
} as const;

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
    page.getByText(`${LARGE_RESULT_COUNT} matching Plans`),
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

async function waitForStableShell(page: Page) {
  await expect(page.locator('[data-bootstrap-state="normal"]')).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
