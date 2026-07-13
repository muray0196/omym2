/**
 * Summary: Verifies the installed shell operates under the frozen production CSP.
 * Why: Detects inline or remote runtime behavior while exercising lazy interactions.
 */
import type { Page } from "@playwright/test";

import { expect, test } from "./playwright-fixtures";
import {
  allM3RoutePaths,
  notFoundRoute,
  operationRecoveryRoute,
} from "./route-fixtures";

const WEB_CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
const LAZY_ROUTE_PATHS = [
  ...allM3RoutePaths,
  operationRecoveryRoute,
  notFoundRoute,
] as const;

test("runs the shell and Command Center without CSP violations", async ({
  page,
}) => {
  test.slow();
  await page.addInitScript(() => {
    const target = globalThis as typeof globalThis & {
      __omym2CspViolations?: Array<{ blockedUri: string; directive: string }>;
    };
    target.__omym2CspViolations = [];
    document.addEventListener("securitypolicyviolation", (event) => {
      target.__omym2CspViolations?.push({
        blockedUri: event.blockedURI,
        directive: event.effectiveDirective,
      });
    });
  });

  for (const path of LAZY_ROUTE_PATHS) {
    const response = await page.goto(path);
    expect(response?.headers()["content-security-policy"]).toBe(
      WEB_CONTENT_SECURITY_POLICY,
    );
    await expect(
      page.locator("[data-omym2-shell-interactive='true']"),
    ).toBeAttached();
    await page.waitForLoadState("networkidle");

    if (path === "/") {
      await page.keyboard.press("Control+k");
      await expect(
        page.getByRole("dialog", { name: "Command Center" }),
      ).toBeVisible();
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: "Close Command Center" }).click();
    }

    expect(await readCspViolations(page), `CSP violations at ${path}`).toEqual(
      [],
    );
  }
});

async function readCspViolations(page: Page) {
  return page.evaluate(() => {
    const target = globalThis as typeof globalThis & {
      __omym2CspViolations?: Array<{ blockedUri: string; directive: string }>;
    };
    return target.__omym2CspViolations ?? [];
  });
}
