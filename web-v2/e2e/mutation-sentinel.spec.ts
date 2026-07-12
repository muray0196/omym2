/**
 * Summary: Proves every M1 Web route leaves the Library music tree byte-for-byte unchanged.
 * Why: Enforces the pre-M4 boundary that the renewed UI cannot mutate music files.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { join, relative } from "node:path";
import { expect, test } from "@playwright/test";

import { allM1RoutePaths } from "./route-fixtures";

test("does not mutate Library music files before M4", async ({ page }) => {
  const applicationRoot = process.env.OMYM2_E2E_APPLICATION_ROOT;
  if (applicationRoot === undefined || applicationRoot.length === 0) {
    throw new Error(
      "OMYM2_E2E_APPLICATION_ROOT must identify the isolated test application root.",
    );
  }

  const libraryRoot = join(applicationRoot, "library");
  const before = await snapshotTree(libraryRoot);
  expect(before.some((entry) => entry.path === "sentinel.flac")).toBe(true);

  for (const route of allM1RoutePaths) {
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

  expect(await snapshotTree(libraryRoot)).toEqual(before);
});

async function snapshotTree(root: string) {
  const paths = await listTree(root);
  return Promise.all(
    paths.map(async (path) => {
      const metadata = await stat(path, { bigint: true });
      const common = {
        modifiedNanoseconds: metadata.mtimeNs.toString(),
        path: relative(root, path),
      };
      if (metadata.isDirectory()) {
        return { ...common, kind: "directory" as const };
      }
      return {
        ...common,
        bytes: (await readFile(path)).toString("base64"),
        kind: "file" as const,
      };
    }),
  );
}

async function listTree(root: string): Promise<string[]> {
  const paths: string[] = [];
  const pending = [root];
  while (pending.length > 0) {
    const directory = pending.pop();
    if (directory === undefined) {
      continue;
    }
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(directory, entry.name);
      paths.push(path);
      if (entry.isDirectory()) {
        pending.push(path);
      }
    }
  }
  return paths.toSorted();
}
