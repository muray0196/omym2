/**
 * Summary: Shares durable Operation acceptance and polling assertions across E2E journeys.
 * Why: Keeps mutation envelopes, terminal reads, and result extraction on one current contract.
 */
import type { Page, Response } from "@playwright/test";

import type {
  ApiEnvelopeOperationRef,
  ApiEnvelopeOperationResource,
  OperationResource,
} from "../src/api/generated";
import { expect } from "./playwright-fixtures";

export function waitForMutation(page: Page, pathname: string) {
  return page.waitForResponse((response) => {
    return (
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === pathname
    );
  });
}

export function waitForSucceededOperation(page: Page) {
  return page.waitForResponse(async (response) => {
    if (!isOperationPoll(response)) return false;
    const envelope = (await response.json()) as ApiEnvelopeOperationResource;
    return envelope.data?.status === "succeeded";
  });
}

export async function requiredOperationReference(response: Response) {
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

export async function requiredOperation(response: Response) {
  const envelope = (await response.json()) as ApiEnvelopeOperationResource;
  if (envelope.data === null) {
    throw new Error("Operation poll did not contain data.");
  }
  expect(envelope.errors).toEqual([]);
  expect(envelope.data.status).toBe("succeeded");
  return envelope.data;
}

export function requiredPlanId(operation: OperationResource) {
  if (operation.result?.kind !== "plan_created") {
    throw new Error("Planning Operation did not return a Plan.");
  }
  return operation.result.plan_id;
}

export function requiredRunId(operation: OperationResource) {
  if (operation.result?.kind !== "run_completed") {
    throw new Error("Apply Operation did not return a completed Run.");
  }
  return operation.result.run_id;
}

export async function startAndCompleteOperation(
  page: Page,
  input: { buttonName: string; pathname: string },
) {
  const acceptance = waitForMutation(page, input.pathname);
  const completion = waitForSucceededOperation(page);
  const button = page.getByRole("button", { name: input.buttonName });
  await expect(button).toBeEnabled();
  await button.click();
  const accepted = await requiredOperationReference(await acceptance);
  const completed = await requiredOperation(await completion);
  expect(completed.operation_id).toBe(accepted.operation_id);
  return completed;
}

function isOperationPoll(response: Response) {
  return (
    response.request().method() === "GET" &&
    /\/api\/operations\/[0-9a-f-]+$/.test(response.url())
  );
}
