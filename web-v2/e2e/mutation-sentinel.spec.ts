/**
 * Summary: Proves non-mutating Web routes leave unrelated Library music unchanged.
 * Why: Keeps passive navigation distinct from the explicit Apply and Undo boundaries.
 */
import { expect, test } from "@playwright/test";

import { snapshotIsolatedLibrary } from "./library-snapshot";
import { allM3RoutePaths } from "./route-fixtures";

test("non-mutating routes preserve an unrelated Library file", async ({
  page,
}) => {
  const before = await sentinelSnapshot();
  expect(before).toBeDefined();

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

  expect(await sentinelSnapshot()).toEqual(before);
});

async function sentinelSnapshot() {
  return (await snapshotIsolatedLibrary()).find(
    (entry) => entry.path === "sentinel.flac",
  );
}
