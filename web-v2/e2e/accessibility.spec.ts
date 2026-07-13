/**
 * Summary: Runs axe against primary M2 clean-room browser states.
 * Why: Makes WCAG regressions in the shell, palette, and fallback independently diagnosable.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { allM2RoutePaths, notFoundRoute } from "./route-fixtures";

for (const path of [...allM2RoutePaths, notFoundRoute]) {
  test(`has no detectable accessibility violations at ${path}`, async ({
    page,
  }) => {
    await page.goto(path);
    await expect(
      page.locator("[data-omym2-shell-interactive='true']"),
    ).toBeAttached();
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
  await page.getByRole("button", { name: "Keyboard shortcuts" }).click();
  await expect(
    page.getByRole("dialog", { name: "Keyboard shortcuts" }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("has no detectable accessibility violations in mobile navigation", async ({
  page,
}) => {
  await page.setViewportSize({ height: 800, width: 375 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
