/**
 * Summary: Exercises real-API planning, execution, Undo, and persisted evidence flows.
 * Why: Proves keyboard-safe mutations use durable Operations and exact filesystem outcomes.
 */
import { readFile, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { Page, Response } from "@playwright/test";

import type {
  ApiEnvelopeOperationRef,
  ApiEnvelopeOperationResource,
  ApiEnvelopePaginatedDataRunHeader,
  ApiEnvelopePlanDetailData,
  OperationResource,
} from "../src/api/generated";
import {
  applyDesktopZoom,
  DESKTOP_ZOOM_EXPECTED_METRICS,
  readDesktopZoomMetrics,
} from "./desktop-zoom";
import { expect, test } from "./playwright-fixtures";
import { snapshotIsolatedLibrary } from "./library-snapshot";

test.describe.configure({ mode: "serial", retries: 0 });

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

test("polls Add and Check to durable results with a 200%-zoom completion", async ({
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
  const zoomSession = await applyDesktopZoom(page);
  await expect
    .poll(() => readDesktopZoomMetrics(page))
    .toEqual(DESKTOP_ZOOM_EXPECTED_METRICS);
  const checkPoll = waitForSucceededOperation(page);
  const runCheck = page.getByRole("button", { name: "Run Check" });
  await expect(runCheck).toBeEnabled();
  await runCheck.focus();
  await runCheck.press("Enter");
  const completedCheck = await requiredOperation(await checkPoll);
  expect(completedCheck.kind).toBe("check");
  expect(completedCheck.result?.kind).toBe("check_completed");
  await expect
    .poll(() => readDesktopZoomMetrics(page))
    .toEqual(DESKTOP_ZOOM_EXPECTED_METRICS);
  await zoomSession.detach();
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

test.describe("execution console", () => {
  test.describe.configure({ mode: "serial", retries: 0 });

  test("applies partial work, reviews evidence, undoes it, and cancels a fresh Plan", async ({
    page,
  }) => {
    const applicationRoot = requiredApplicationRoot();
    const incomingSuccess = join(applicationRoot, "incoming", "A-Success.flac");
    const incomingFailure = join(applicationRoot, "incoming", "Z-Failure.flac");
    const librarySuccess = join(applicationRoot, "library", "A-Success.flac");
    const libraryFailure = join(applicationRoot, "library", "Z-Failure.flac");
    const successBytes = await readFile(incomingSuccess);

    expect(await fileExists(incomingFailure)).toBe(true);
    expect(await fileExists(librarySuccess)).toBe(false);
    expect(await fileExists(libraryFailure)).toBe(false);

    const addPlanId = await createAddPlanByKeyboard(page);
    const actions = page.getByRole("list", { name: "Recorded actions" });
    await expect(
      actions.getByText("A-Success.flac", { exact: true }),
    ).toBeVisible();
    await expect(
      actions.getByText("Z-Failure.flac", { exact: true }),
    ).toBeVisible();

    await writeFile(libraryFailure, "E2E apply-time target conflict.\n", {
      flag: "wx",
    });

    const applyAcceptance = waitForMutation(
      page,
      `/api/plans/${addPlanId}/apply`,
    );
    const applyCompletion = waitForSucceededOperation(page);
    const applyButton = page.getByRole("button", { name: "Apply Plan" });
    await expect(applyButton).toBeEnabled();
    await applyButton.focus();
    await applyButton.press("Enter");

    const acceptedApply = await requiredOperationReference(
      await applyAcceptance,
    );
    const completedApply = await requiredOperation(await applyCompletion);
    expect(completedApply.operation_id).toBe(acceptedApply.operation_id);
    expect(completedApply.kind).toBe("apply_plan");
    expect(completedApply.plan_id).toBe(addPlanId);
    expect(completedApply.run_id).not.toBeNull();
    expect(completedApply.result?.kind).toBe("run_completed");

    const sourceRunId = requiredRunId(completedApply);
    await expect(page).toHaveURL(`/history/${sourceRunId}`);
    await expect(
      page.getByRole("heading", { name: "Run detail" }),
    ).toBeFocused();
    await expect(
      page.getByText("Partially failed", { exact: true }),
    ).toBeVisible();
    await expectRunEventEvidence(page, { failed: 1, succeeded: 1 });

    expect(await readFile(librarySuccess)).toEqual(successBytes);
    expect(await fileExists(incomingSuccess)).toBe(false);
    expect(await fileExists(incomingFailure)).toBe(true);
    expect(await fileExists(libraryFailure)).toBe(true);

    const undoAcceptance = waitForMutation(
      page,
      `/api/history/${sourceRunId}/undo-plan`,
    );
    const undoCompletion = waitForSucceededOperation(page);
    const createUndoPlan = page.getByRole("button", {
      name: "Create Undo Plan",
    });
    await expect(createUndoPlan).toBeEnabled();
    await createUndoPlan.focus();
    await createUndoPlan.press("Enter");

    const acceptedUndo = await requiredOperationReference(await undoAcceptance);
    const completedUndo = await requiredOperation(await undoCompletion);
    expect(completedUndo.operation_id).toBe(acceptedUndo.operation_id);
    expect(completedUndo.kind).toBe("undo_plan");
    expect(completedUndo.result?.kind).toBe("plan_created");
    const undoPlanId = requiredPlanId(completedUndo);

    await expect(page).toHaveURL(`/plans/${undoPlanId}`);
    await expect(
      page.getByRole("heading", { name: "Plan detail" }),
    ).toBeFocused();
    await expect(page.getByText("Undo", { exact: true })).toBeVisible();
    const undoActions = page.getByRole("list", { name: "Recorded actions" });
    await expect(
      undoActions.getByText("A-Success.flac", { exact: true }),
    ).toBeVisible();
    await expect(
      undoActions.getByText(incomingSuccess, { exact: true }),
    ).toBeVisible();

    const undoApplyAcceptance = waitForMutation(
      page,
      `/api/plans/${undoPlanId}/apply`,
    );
    const undoApplyCompletion = waitForSucceededOperation(page);
    const applyUndoButton = page.getByRole("button", { name: "Apply Plan" });
    await expect(applyUndoButton).toBeEnabled();
    await applyUndoButton.focus();
    await applyUndoButton.press("Enter");

    const acceptedUndoApply = await requiredOperationReference(
      await undoApplyAcceptance,
    );
    const completedUndoApply = await requiredOperation(
      await undoApplyCompletion,
    );
    expect(completedUndoApply.operation_id).toBe(
      acceptedUndoApply.operation_id,
    );
    expect(completedUndoApply.kind).toBe("apply_plan");
    expect(completedUndoApply.plan_id).toBe(undoPlanId);
    const undoRunId = requiredRunId(completedUndoApply);

    await expect(page).toHaveURL(`/history/${undoRunId}`);
    await expect(
      page.getByText("Succeeded", { exact: true }).first(),
    ).toBeVisible();
    await expectRunEventEvidence(page, { failed: 0, succeeded: 1 });
    expect(await readFile(incomingSuccess)).toEqual(successBytes);
    expect(await fileExists(librarySuccess)).toBe(false);

    const freshPlanId = await createAddPlanByKeyboard(page);
    await expect(page.getByText("Ready", { exact: true })).toBeVisible();
    const libraryBeforeCancel = await snapshotIsolatedLibrary();
    const cancelResponse = waitForMutation(
      page,
      `/api/plans/${freshPlanId}/cancel`,
    );
    const cancelButton = page.getByRole("button", { name: "Cancel Plan" });
    await expect(cancelButton).toBeEnabled();
    await cancelButton.focus();
    await cancelButton.press("Enter");
    const cancellationDialog = page.getByRole("dialog", {
      name: "Cancel this Plan?",
    });
    await expect(cancellationDialog).toBeVisible();
    await expect(
      cancellationDialog.getByRole("button", { name: "Keep Plan" }),
    ).toBeFocused();
    const cancellationAxeResults = await new AxeBuilder({ page })
      .include("dialog[open]")
      .analyze();
    expect(cancellationAxeResults.violations).toEqual([]);
    await page.keyboard.press("Tab");
    const confirmCancellation = cancellationDialog.getByRole("button", {
      name: "Cancel this Plan",
    });
    await expect(confirmCancellation).toBeFocused();
    await confirmCancellation.press("Enter");

    const cancelledPlan = await requiredPlanDetail(await cancelResponse);
    expect(cancelledPlan.plan.status).toBe("cancelled");
    await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Apply Plan" }),
    ).toBeDisabled();
    expect(await snapshotIsolatedLibrary()).toEqual(libraryBeforeCancel);

    const cancelledHistoryResponse = await page.request.get(
      `/api/history?plan_id=${freshPlanId}`,
    );
    expect(cancelledHistoryResponse.ok()).toBe(true);
    const cancelledHistory =
      (await cancelledHistoryResponse.json()) as ApiEnvelopePaginatedDataRunHeader;
    expect(cancelledHistory.data?.items).toEqual([]);
  });
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

async function createAddPlanByKeyboard(page: Page) {
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
  return requiredPathIdentifier(page.url(), "plans");
}

function waitForMutation(page: Page, pathname: string) {
  return page.waitForResponse((response) => {
    return (
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === pathname
    );
  });
}

async function requiredOperationReference(response: Response) {
  expect(response.status()).toBe(202);
  const envelope = (await response.json()) as ApiEnvelopeOperationRef;
  if (envelope.data === null) {
    throw new Error("Accepted Operation response did not contain data.");
  }
  expect(envelope.errors).toEqual([]);
  expect(envelope.data.status_url).toBe(
    `/api/operations/${envelope.data.operation_id}`,
  );
  return envelope.data;
}

async function requiredOperation(response: Response) {
  const envelope = (await response.json()) as ApiEnvelopeOperationResource;
  if (envelope.data === null) {
    throw new Error("Operation poll did not contain data.");
  }
  expect(envelope.errors).toEqual([]);
  expect(envelope.data.status).toBe("succeeded");
  return envelope.data;
}

async function requiredPlanDetail(response: Response) {
  expect(response.status()).toBe(200);
  const envelope = (await response.json()) as ApiEnvelopePlanDetailData;
  if (envelope.data === null) {
    throw new Error("Plan mutation response did not contain data.");
  }
  expect(envelope.errors).toEqual([]);
  return envelope.data;
}

function requiredRunId(operation: OperationResource) {
  if (operation.result?.kind !== "run_completed") {
    throw new Error("Apply Operation did not return a completed Run.");
  }
  return operation.result.run_id;
}

function requiredPlanId(operation: OperationResource) {
  if (operation.result?.kind !== "plan_created") {
    throw new Error("Planning Operation did not return a Plan.");
  }
  return operation.result.plan_id;
}

function requiredPathIdentifier(url: string, resource: string) {
  const segments = new URL(url).pathname.split("/").filter(Boolean);
  if (segments.length !== 2 || segments[0] !== resource) {
    throw new Error(`Expected a ${resource} detail URL, received ${url}.`);
  }
  const identifier = segments[1];
  if (identifier === undefined || identifier.length === 0) {
    throw new Error(`Expected a ${resource} identifier in ${url}.`);
  }
  return identifier;
}

async function expectRunEventEvidence(
  page: Page,
  expected: { failed: number; succeeded: number },
) {
  const evidence = page
    .getByRole("heading", { name: "File mutation evidence" })
    .locator("..");
  const events = evidence.getByRole("listitem");
  await expect(events).toHaveCount(expected.failed + expected.succeeded);
  await expect(events.filter({ hasText: "Succeeded" })).toHaveCount(
    expected.succeeded,
  );
  await expect(events.filter({ hasText: "Failed" })).toHaveCount(
    expected.failed,
  );
}

async function fileExists(path: string) {
  try {
    await stat(path);
  } catch (error) {
    if (isMissingFileError(error)) return false;
    throw error;
  }
  return true;
}

function isMissingFileError(error: unknown) {
  return (
    error instanceof Error &&
    "code" in error &&
    (error as NodeJS.ErrnoException).code === "ENOENT"
  );
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
