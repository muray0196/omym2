/**
 * Summary: Exercises first-run recovery through successful and blocked Plan evidence.
 * Why: Proves isolated onboarding keeps every Library music mutation Plan-centered.
 */
import AxeBuilder from "@axe-core/playwright";
import { copyFile, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import type { Page } from "@playwright/test";

import type {
  ApiEnvelopePaginatedDataFileEventResource,
  ApiEnvelopePaginatedDataPlanActionResource,
  PlanActionResource,
} from "../src/api/generated";
import { expect, test } from "./playwright-fixtures";
import {
  requiredPlanId,
  requiredRunId,
  startAndCompleteOperation,
} from "./operation-helpers";

const FIRST_RUN_FIXTURE_PROFILE = "first-run";
const ORGANIZE_SOURCE_FILE_NAME = "Needs-Organizing.flac";
const ORGANIZE_TARGET_PATH = "Organized-Title.flac";
const ADD_SUCCESS_FILE_NAME = "First-Run-Success.flac";
const ADD_SUCCESS_TARGET_PATH = "First-Run-Success.flac";
const ADD_BLOCKED_FILE_NAME = "Blocked-Arrival.flac";
const ADD_BLOCKED_TARGET_PATH = "Blocked-Arrival.flac";
const PATH_POLICY_TEMPLATE = "{title}";
const E2E_PAGE_LIMIT = 100;

test.describe.configure({ retries: 0 });

test.skip(
  process.env.OMYM2_E2E_FIXTURE_PROFILE !== FIRST_RUN_FIXTURE_PROFILE,
  "This journey requires the isolated first-run fixture profile.",
);

test("recovers first run through both Organize outcomes and successful blocked-aware Add @first-run", async ({
  page,
}) => {
  test.slow();
  const applicationRoot = requiredApplicationRoot();
  const configPath = join(applicationRoot, ".config", "config.toml");
  const libraryRoot = join(applicationRoot, "library");
  const incomingRoot = join(applicationRoot, "incoming");
  const organizeSource = join(libraryRoot, ORGANIZE_SOURCE_FILE_NAME);
  const organizeTarget = join(libraryRoot, ORGANIZE_TARGET_PATH);
  const addSuccessSource = join(incomingRoot, ADD_SUCCESS_FILE_NAME);
  const addSuccessTarget = join(libraryRoot, ADD_SUCCESS_TARGET_PATH);
  const addBlockedSource = join(incomingRoot, ADD_BLOCKED_FILE_NAME);
  const addBlockedTarget = join(libraryRoot, ADD_BLOCKED_TARGET_PATH);
  const organizeBytes = await readFile(organizeSource);
  const addSuccessBytes = await readFile(addSuccessSource);
  const addBlockedBytes = await readFile(addBlockedSource);

  expect(await fileExists(configPath)).toBe(false);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Operations overview" }),
  ).toBeFocused();
  await expect(
    page.getByRole("alert").filter({
      hasText: "No registered Library is available.",
    }),
  ).toBeVisible();

  await recoverSettings(page, { incomingRoot, libraryRoot });
  expect(await fileExists(configPath)).toBe(true);

  const organizePlan = await createOrganizePlan(page, libraryRoot);
  expect(organizePlan.kind).toBe("organize_plan");
  expect(organizePlan.result?.kind).toBe("plan_created");
  const organizePlanId = requiredPlanId(organizePlan);
  const organizeActions = await readPlanActions(page, organizePlanId);
  expect(organizeActions).toHaveLength(1);
  expect(organizeActions[0]).toMatchObject({
    action_type: "move",
    reason: null,
    source_path: ORGANIZE_SOURCE_FILE_NAME,
    status: "planned",
    target_path: ORGANIZE_TARGET_PATH,
  });
  expect(await readFile(organizeSource)).toEqual(organizeBytes);
  expect(await fileExists(organizeTarget)).toBe(false);
  await expect(
    page
      .getByRole("list", { name: "Recorded actions" })
      .getByText(ORGANIZE_TARGET_PATH, { exact: true }),
  ).toBeVisible();
  await expectNoAxeViolations(page);

  const organizeRun = await applyCurrentPlan(page, organizePlanId);
  const organizeRunId = requiredRunId(organizeRun);
  await expect(page).toHaveURL(`/history/${organizeRunId}`);
  await expect(page.getByRole("heading", { name: "Run detail" })).toBeFocused();
  await expectRunEventEvidence(page, { failed: 0, succeeded: 1 });
  expect(await readFile(organizeTarget)).toEqual(organizeBytes);
  expect(await fileExists(organizeSource)).toBe(false);

  const registration = await organizeWithoutPlan(page, libraryRoot);
  expect(registration.kind).toBe("organize_plan");
  expect(registration.result).toMatchObject({
    kind: "registered_without_plan",
    track_count: 1,
  });
  await expect(page).toHaveURL("/library");
  await expect(
    page.getByRole("heading", { level: 1, name: "Library" }),
  ).toBeFocused();

  // Fixture setup only: occupy the reviewed Add target with different audio
  // after registration so planning must persist a target_exists block.
  await copyFile(organizeTarget, addBlockedTarget);
  const occupiedTargetBytes = await readFile(addBlockedTarget);

  const addPlan = await createAddPlan(page);
  expect(addPlan.kind).toBe("add_plan");
  expect(addPlan.result?.kind).toBe("plan_created");
  const addPlanId = requiredPlanId(addPlan);
  const addActions = await readPlanActions(page, addPlanId);
  expect(addActions).toHaveLength(2);
  expect(findAction(addActions, addSuccessSource)).toMatchObject({
    action_type: "move",
    reason: null,
    source_path: addSuccessSource,
    status: "planned",
    target_path: ADD_SUCCESS_TARGET_PATH,
  });
  expect(findAction(addActions, addBlockedSource)).toMatchObject({
    action_type: "move",
    reason: "target_exists",
    source_path: addBlockedSource,
    status: "blocked",
    target_path: ADD_BLOCKED_TARGET_PATH,
  });
  expect(await readFile(addSuccessSource)).toEqual(addSuccessBytes);
  expect(await fileExists(addSuccessTarget)).toBe(false);
  expect(await readFile(addBlockedSource)).toEqual(addBlockedBytes);
  expect(await readFile(addBlockedTarget)).toEqual(occupiedTargetBytes);
  const recordedActions = page.getByRole("list", { name: "Recorded actions" });
  await expect(
    recordedActions.getByText("Target already exists", { exact: true }),
  ).toBeVisible();
  await expect(
    recordedActions.getByText(addBlockedSource, { exact: true }),
  ).toBeVisible();
  await expectNoAxeViolations(page);

  const addRun = await applyCurrentPlan(page, addPlanId);
  const addRunId = requiredRunId(addRun);
  await expect(page).toHaveURL(`/history/${addRunId}`);
  await expect(page.getByRole("heading", { name: "Run detail" })).toBeFocused();
  await expect(
    page.getByText("Succeeded", { exact: true }).first(),
  ).toBeVisible();
  await expectRunEventEvidence(page, { failed: 0, succeeded: 1 });

  expect(await readFile(addSuccessTarget)).toEqual(addSuccessBytes);
  expect(await fileExists(addSuccessSource)).toBe(false);
  expect(await readFile(addBlockedSource)).toEqual(addBlockedBytes);
  expect(await readFile(addBlockedTarget)).toEqual(occupiedTargetBytes);

  const completedActions = await readPlanActions(page, addPlanId);
  expect(findAction(completedActions, addSuccessSource).status).toBe("applied");
  expect(findAction(completedActions, addBlockedSource)).toMatchObject({
    reason: "target_exists",
    status: "blocked",
  });
  const fileEvents = await readRunEvents(page, addRunId);
  expect(fileEvents).toHaveLength(1);
  expect(fileEvents[0]).toMatchObject({
    error_code: null,
    source_path: addSuccessSource,
    status: "succeeded",
    target_path: ADD_SUCCESS_TARGET_PATH,
  });
  await expectNoAxeViolations(page);

  await page.reload();
  await expect(page).toHaveURL(`/history/${addRunId}`);
  await expectRunEventEvidence(page, { failed: 0, succeeded: 1 });
  await page.goto("/history");
  await expect(
    page.getByRole("link").filter({ hasText: addRunId }),
  ).toBeVisible();
});

async function recoverSettings(
  page: Page,
  paths: { incomingRoot: string; libraryRoot: string },
) {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeFocused();
  const persisted = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === "/api/settings" &&
      response.status() === 200,
  );
  await page
    .getByRole("textbox", { name: "Library path" })
    .fill(paths.libraryRoot);
  await page
    .getByRole("textbox", { name: "Incoming path" })
    .fill(paths.incomingRoot);
  await page
    .getByRole("textbox", { name: "Path template" })
    .fill(PATH_POLICY_TEMPLATE);
  await persisted;
  await expect(
    page.getByRole("status").filter({
      has: page.getByRole("heading", { name: "Automatic save" }),
    }),
  ).toContainText("Saved");
}

async function createOrganizePlan(page: Page, libraryRoot: string) {
  await page.goto("/plans/new/organize");
  await page.getByRole("textbox", { name: "Library root" }).fill(libraryRoot);
  const completed = await startAndCompleteOperation(page, {
    buttonName: "Scan Library",
    pathname: "/api/plans/organize",
  });
  await expect(page).toHaveURL(/\/plans\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();
  return completed;
}

async function organizeWithoutPlan(page: Page, libraryRoot: string) {
  await page.goto("/plans/new/organize");
  await page.getByRole("textbox", { name: "Library root" }).fill(libraryRoot);
  return startAndCompleteOperation(page, {
    buttonName: "Scan Library",
    pathname: "/api/plans/organize",
  });
}

async function createAddPlan(page: Page) {
  await page.goto("/plans/new/add");
  const completed = await startAndCompleteOperation(page, {
    buttonName: "Scan and create Plan",
    pathname: "/api/plans/add",
  });
  await expect(page).toHaveURL(/\/plans\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { name: "Plan detail" }),
  ).toBeFocused();
  return completed;
}

async function applyCurrentPlan(page: Page, planId: string) {
  return startAndCompleteOperation(page, {
    buttonName: "Apply Plan",
    pathname: `/api/plans/${planId}/apply`,
  });
}

async function readPlanActions(page: Page, planId: string) {
  const response = await page.request.get(
    `/api/plans/${planId}/actions?limit=${E2E_PAGE_LIMIT}`,
  );
  expect(response.ok()).toBe(true);
  const envelope =
    (await response.json()) as ApiEnvelopePaginatedDataPlanActionResource;
  expect(envelope.errors).toEqual([]);
  if (envelope.data === null) {
    throw new Error("PlanAction response did not contain data.");
  }
  return envelope.data.items;
}

async function readRunEvents(page: Page, runId: string) {
  const response = await page.request.get(
    `/api/history/${runId}/events?limit=${E2E_PAGE_LIMIT}`,
  );
  expect(response.ok()).toBe(true);
  const envelope =
    (await response.json()) as ApiEnvelopePaginatedDataFileEventResource;
  expect(envelope.errors).toEqual([]);
  if (envelope.data === null) {
    throw new Error("FileEvent response did not contain data.");
  }
  return envelope.data.items;
}

function findAction(actions: PlanActionResource[], sourcePath: string) {
  const action = actions.find(
    (candidate) => candidate.source_path === sourcePath,
  );
  if (action === undefined) {
    throw new Error(`No PlanAction recorded source ${sourcePath}.`);
  }
  return action;
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

async function expectNoAxeViolations(page: Page) {
  await expect(
    page.locator("[role='status']").filter({ hasText: /Loading|Opening/ }),
  ).toHaveCount(0);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
}

function requiredApplicationRoot() {
  const applicationRoot = process.env.OMYM2_E2E_APPLICATION_ROOT;
  if (applicationRoot === undefined || applicationRoot.length === 0) {
    throw new Error(
      "OMYM2_E2E_APPLICATION_ROOT must identify the isolated test application root.",
    );
  }
  return applicationRoot;
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
