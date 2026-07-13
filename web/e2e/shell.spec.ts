/**
 * Summary: Exercises the installed clean-room shell and keyboard Command Center.
 * Why: Verifies browser behavior against the real FastAPI static-serving boundary.
 */
import { expect, test } from "./playwright-fixtures";
import { deepPlanRoute, notFoundRoute } from "./route-fixtures";

test("opens Command Center by keyboard and restores route focus", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.locator("[data-omym2-shell-interactive='true']"),
  ).toBeAttached();
  await expect(
    page.getByRole("heading", { name: "Operations overview" }),
  ).toBeFocused();
  await expect(page.getByRole("navigation", { name: "Primary navigation" }))
    .toMatchAriaSnapshot(`
    - navigation "Primary navigation":
      - link "Overview"
      - link "Plans"
      - link "Library"
      - link "Health"
      - link "History"
      - link "Settings"
  `);

  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", {
    name: "Search commands and navigation",
  });
  await expect(search).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/plans$/);
  await expect(page.getByRole("heading", { name: "Plans" })).toBeFocused();
});

test("keeps the original focus target across a repeated Command Center shortcut", async ({
  page,
}) => {
  await page.goto("/");
  const trigger = page
    .getByRole("complementary")
    .getByRole("button", { name: "Command Center" });
  await trigger.focus();

  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("combobox", { name: "Search commands and navigation" }),
  ).toBeFocused();
  await page.keyboard.press("Control+k");
  await page.keyboard.press("Escape");

  await expect(
    page.getByRole("dialog", { name: "Command Center" }),
  ).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("renders the React fallback for an unmatched HTML route", async ({
  page,
}) => {
  await page.goto(notFoundRoute);
  await expect(
    page.getByRole("heading", { name: "This route does not exist" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Return to overview" }),
  ).toBeVisible();
});

test("restores a matched detail route after a direct load and reload", async ({
  page,
}) => {
  await page.goto(deepPlanRoute);
  await expect(
    page.getByRole("heading", { name: "Plan not found" }),
  ).toBeVisible();

  await page.reload();

  await expect(page).toHaveURL(new RegExp(`${deepPlanRoute}$`));
  await expect(
    page.getByRole("heading", { name: "Plan not found" }),
  ).toBeFocused();
});
