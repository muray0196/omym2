/**
 * Summary: Proves every M3 Web route leaves the Library music tree byte-for-byte unchanged.
 * Why: Enforces the pre-M4 boundary that the renewed UI cannot mutate music files.
 */
import { expect, test } from "@playwright/test";

import { snapshotIsolatedLibrary } from "./library-snapshot";
import { allM3RoutePaths } from "./route-fixtures";

test("does not mutate Library music files before M4", async ({ page }) => {
  const before = await snapshotIsolatedLibrary();
  expect(before.some((entry) => entry.path === "sentinel.flac")).toBe(true);

  for (const route of allM3RoutePaths) {
    await page.goto(route);
    await expect(
      page.locator("[data-omym2-shell-interactive='true']"),
    ).toBeAttached();
  }

  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Command Center" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close Command Center" }).click();
  await page.setViewportSize({ height: 800, width: 375 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await page.getByRole("button", { name: "Close navigation" }).click();

  expect(await snapshotIsolatedLibrary()).toEqual(before);
});
