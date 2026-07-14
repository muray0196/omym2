/**
 * Summary: Runs axe against primary bundled Web browser states.
 * Why: Makes WCAG regressions in the shell, palette, and fallback independently diagnosable.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import type {
  ApiEnvelopeBootstrapData,
  ApiEnvelopePaginatedDataTrackResource,
} from "../src/api/generated";
import {
  applyDesktopZoom,
  DESKTOP_ZOOM_EXPECTED_METRICS,
  readDesktopZoomMetrics,
} from "./desktop-zoom";
import { expect, test } from "./playwright-fixtures";
import { allM3RoutePaths, notFoundRoute } from "./route-fixtures";

const ROUTE_HEADINGS = new Map<string, string>([
  ["/", "Operations overview"],
  ["/plans", "Plans"],
  ["/plans/new/add", "Add music"],
  ["/plans/new/organize", "Organize Library"],
  ["/plans/new/refresh", "Refresh metadata"],
  ["/plans/018f0000-0000-7000-8000-000000000010", "Plan not found"],
  ["/library", "Library"],
  ["/library/018f0000-0000-7000-8000-000000000020", "Track not found"],
  ["/health", "Health"],
  ["/history", "History"],
  ["/history/018f0000-0000-7000-8000-000000000030", "Run detail"],
  ["/settings", "Settings"],
  [notFoundRoute, "This route does not exist"],
]);

for (const path of [...allM3RoutePaths, notFoundRoute]) {
  test(`has no detectable accessibility violations at ${path}`, async ({
    page,
  }) => {
    await page.goto(path);
    await expect(
      page.locator("[data-omym2-shell-interactive='true']"),
    ).toBeAttached();
    await waitForRouteReady(page, path);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
}

test("has no detectable accessibility violations in Command Center", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.locator("[data-omym2-shell-interactive='true']"),
  ).toBeAttached();
  await waitForRouteReady(page, "/");
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Command Center" }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);

  await page
    .getByRole("combobox", { name: "Search commands and navigation" })
    .fill("no matching destination");
  await expect(
    page.getByText("No commands or destinations match your search."),
  ).toBeVisible();
  const emptyResults = await new AxeBuilder({ page }).analyze();
  expect(emptyResults.violations).toEqual([]);
});

test("has no detectable accessibility violations in shortcut help", async ({
  page,
}) => {
  await page.goto("/");
  await waitForRouteReady(page, "/");
  await page.getByRole("button", { name: "Keyboard shortcuts" }).click();
  await expect(
    page.getByRole("dialog", { name: "Keyboard shortcuts" }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("has no detectable accessibility violations at 200% desktop zoom", async ({
  page,
}) => {
  await page.goto("/settings");
  await waitForRouteReady(page, "/settings");
  const zoomSession = await applyDesktopZoom(page);
  await expect
    .poll(() => readDesktopZoomMetrics(page))
    .toEqual(DESKTOP_ZOOM_EXPECTED_METRICS);
  await expect(
    page.getByRole("heading", { level: 1, name: "Settings" }),
  ).toBeVisible();
  const primaryAction = page.getByRole("button", { name: "Save Settings" });
  await expect(primaryAction).toBeVisible();
  const geometry = await primaryAction.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const viewport = globalThis.visualViewport;
    return {
      actionLeft: bounds.left,
      actionRight: bounds.right,
      documentOverflows:
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
      viewportLeft: viewport?.offsetLeft ?? 0,
      viewportRight: (viewport?.offsetLeft ?? 0) + (viewport?.width ?? 0),
    };
  });
  expect(geometry.documentOverflows).toBe(false);
  expect(geometry.actionLeft).toBeGreaterThanOrEqual(geometry.viewportLeft);
  expect(geometry.actionRight).toBeLessThanOrEqual(geometry.viewportRight);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await zoomSession.detach();
});

test("has no detectable accessibility violations on a loaded Track detail", async ({
  page,
}) => {
  const bootstrapResponse = await page.request.get("/api/bootstrap");
  const bootstrap =
    (await bootstrapResponse.json()) as ApiEnvelopeBootstrapData;
  const libraryId = bootstrap.data?.active_library?.library_id;
  if (libraryId === undefined) {
    throw new Error("Registered accessibility fixture has no active Library.");
  }
  const tracksResponse = await page.request.get(
    `/api/tracks?library_id=${encodeURIComponent(libraryId)}&limit=1`,
  );
  const tracks =
    (await tracksResponse.json()) as ApiEnvelopePaginatedDataTrackResource;
  const track = tracks.data?.items[0];
  if (track === undefined) {
    throw new Error("Registered accessibility fixture has no Track.");
  }
  const trackTitle = track.metadata.title;
  if (trackTitle === null) {
    throw new Error("Registered accessibility fixture Track has no title.");
  }

  await page.goto(`/library/${track.track_id}`);
  await expect(
    page.getByRole("heading", { level: 1, name: trackTitle }),
  ).toBeFocused();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("has no detectable accessibility violations in the unsaved Settings dialog", async ({
  page,
}) => {
  await page.goto("/settings");
  await waitForRouteReady(page, "/settings");
  const incoming = page.getByRole("textbox", { name: "Incoming path" });
  await incoming.fill(`${await incoming.inputValue()}-draft`);
  await page
    .getByRole("complementary")
    .getByRole("link", { name: "Plans", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Leave with unsaved Settings?" }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("honors reduced-motion preferences for interactive controls", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await waitForRouteReady(page, "/");

  const motion = await page
    .getByRole("button", { name: "Keyboard shortcuts" })
    .evaluate((button) => {
      const toMilliseconds = (duration: string) =>
        duration.endsWith("ms")
          ? Number.parseFloat(duration)
          : Number.parseFloat(duration) * 1000;
      const rootStyle = getComputedStyle(document.documentElement);
      const configured = toMilliseconds(
        rootStyle.getPropertyValue("--motion-reduced").trim(),
      );
      const transitionDurations = getComputedStyle(button)
        .transitionDuration.split(",")
        .map((duration) => toMilliseconds(duration.trim()));
      return {
        configured,
        maximumTransition: Math.max(...transitionDurations),
        reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
      };
    });

  expect(motion.reduced).toBe(true);
  expect(motion.maximumTransition).toBeLessThanOrEqual(motion.configured);
});

async function waitForRouteReady(page: Page, path: string) {
  const heading = ROUTE_HEADINGS.get(path);
  if (heading === undefined) {
    throw new Error(`No loaded-state heading is defined for ${path}.`);
  }
  await expect(
    page.getByRole("heading", { level: 1, name: heading }),
  ).toBeVisible();
  await expect(
    page
      .locator("[role='status']")
      .filter({ hasText: /Connecting|Loading|Opening/ }),
  ).toHaveCount(0);
}
