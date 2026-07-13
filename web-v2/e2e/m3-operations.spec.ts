/**
 * Summary: Exercises real-API M3 Settings, planning, and persisted Check flows.
 * Why: Proves keyboard-safe mutations poll to durable results without moving music files.
 */
import { join } from "node:path";
import { expect, test, type Page, type Response } from "@playwright/test";

import type { ApiEnvelopeOperationResource } from "../src/api/generated";
import { snapshotIsolatedLibrary } from "./library-snapshot";

test.describe.configure({ mode: "serial" });

test("previews and atomically saves Settings by keyboard", async ({ page }) => {
  const libraryBefore = await snapshotIsolatedLibrary();
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeFocused();

  const sampleTitle = page.getByRole("textbox", { name: "Sample title" });
  await sampleTitle.focus();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("Browser Preview");
  const updatePreview = page.getByRole("button", { name: "Update preview" });
  await updatePreview.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("status").filter({ hasText: /Browser-Preview/ }),
  ).toBeVisible();

  const requireAlbum = page.getByRole("checkbox", { name: "Require album" });
  const originalRequireAlbum = await requireAlbum.isChecked();
  await requireAlbum.focus();
  await page.keyboard.press("Space");
  expect(await requireAlbum.isChecked()).toBe(!originalRequireAlbum);

  const review = page.getByRole("button", { name: "Review changes" });
  await review.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByText("Backend validation passed.").first(),
  ).toBeVisible();
  const save = page.getByRole("button", { name: "Save Settings" });
  await save.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Settings saved." }),
  ).toBeVisible();

  expect(await snapshotIsolatedLibrary()).toEqual(libraryBefore);
});

test("polls Add and Check to durable results with reloadable evidence", async ({
  page,
}) => {
  const libraryBefore = await snapshotIsolatedLibrary();
  await page.goto("/plans/new/add");
  const operationPoll = waitForSucceededOperation(page);
  const createPlan = page.getByRole("button", {
    name: "Scan and create Plan",
  });
  await expect(createPlan).toBeEnabled();
  await createPlan.focus();
  await createPlan.press("Enter");
  await operationPoll;

  await expect(page).toHaveURL(/\/plans\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();
  const planUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(planUrl);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();

  await page.goto("/health");
  const checkPoll = waitForSucceededOperation(page);
  const runCheck = page.getByRole("button", { name: "Run Check" });
  await expect(runCheck).toBeEnabled();
  await runCheck.focus();
  await runCheck.press("Enter");
  await checkPoll;
  await expect(
    page.getByText(/Persisted Health has been refreshed/),
  ).toBeVisible();
  const findings = page
    .getByRole("heading", { name: "Findings" })
    .locator("..");
  await expect(
    findings.getByText("Unmanaged file exists").first(),
  ).toBeVisible();

  await page.reload();
  await expect(
    findings.getByText("Unmanaged file exists").first(),
  ).toBeVisible();
  await expect(page.getByText(/Findings checked/)).toBeVisible();
  expect(await snapshotIsolatedLibrary()).toEqual(libraryBefore);
});

test("polls Organize registration and Refresh planning without moving the sentinel", async ({
  page,
}) => {
  const libraryBefore = await snapshotIsolatedLibrary();
  const applicationRoot = requiredApplicationRoot();

  await page.goto("/plans/new/organize");
  const libraryRoot = page.getByRole("textbox", { name: "Library root" });
  await libraryRoot.focus();
  await page.keyboard.type(join(applicationRoot, "library"));
  const organizePoll = waitForSucceededOperation(page);
  const scanLibrary = page.getByRole("button", { name: "Scan Library" });
  await expect(scanLibrary).toBeEnabled();
  await scanLibrary.focus();
  await scanLibrary.press("Enter");
  await organizePoll;

  await expect(page).toHaveURL(/\/library$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Library" }),
  ).toBeFocused();
  await expect(page.getByRole("link", { name: /sentinel/i })).toBeVisible();

  await page.goto("/plans/new/refresh");
  const allScope = page.getByRole("radio", { name: "Entire Library" });
  await allScope.focus();
  await page.keyboard.press("Space");
  const refreshPoll = waitForSucceededOperation(page);
  const createRefresh = page.getByRole("button", {
    name: "Create Refresh Plan",
  });
  await expect(createRefresh).toBeEnabled();
  await createRefresh.focus();
  await createRefresh.press("Enter");
  await refreshPoll;

  await expect(page).toHaveURL(/\/plans\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();
  await expect(page.getByText("Refresh", { exact: true })).toBeVisible();
  await expect(
    page.getByText("This Plan has no recorded actions."),
  ).toBeVisible();
  const refreshPlanUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(refreshPlanUrl);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();

  expect(await snapshotIsolatedLibrary()).toEqual(libraryBefore);
});

function requiredApplicationRoot() {
  const applicationRoot = process.env.OMYM2_E2E_APPLICATION_ROOT;
  if (applicationRoot === undefined || applicationRoot.length === 0) {
    throw new Error(
      "OMYM2_E2E_APPLICATION_ROOT must identify the isolated test application root.",
    );
  }
  return applicationRoot;
}

function waitForSucceededOperation(page: Page) {
  return page.waitForResponse(async (response) => {
    if (!isOperationPoll(response)) return false;
    const envelope = (await response.json()) as ApiEnvelopeOperationResource;
    return envelope.data?.status === "succeeded";
  });
}

function isOperationPoll(response: Response) {
  return (
    response.request().method() === "GET" &&
    /\/api\/operations\/[0-9a-f-]+$/.test(response.url())
  );
}
