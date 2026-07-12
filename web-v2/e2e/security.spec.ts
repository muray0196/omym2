/**
 * Summary: Verifies the installed shell operates under the frozen production CSP.
 * Why: Detects inline or remote runtime behavior while exercising lazy interactions.
 */
import { expect, test } from "@playwright/test";

test("runs the shell and Command Center without CSP violations", async ({
  page,
}) => {
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

  const response = await page.goto("/");
  const policy = response?.headers()["content-security-policy"];
  expect(policy).toContain("default-src 'self'");
  expect(policy).toContain("script-src 'self'");
  expect(policy).toContain("object-src 'none'");
  expect(policy).toContain("base-uri 'none'");
  expect(policy).toContain("frame-ancestors 'none'");
  expect(policy).not.toContain("unsafe-inline");
  expect(policy).not.toContain("unsafe-eval");

  await expect(
    page.locator("[data-omym2-shell-interactive='true']"),
  ).toBeAttached();
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Command Center" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close Command Center" }).click();

  const violations = await page.evaluate(() => {
    const target = globalThis as typeof globalThis & {
      __omym2CspViolations?: Array<{ blockedUri: string; directive: string }>;
    };
    return target.__omym2CspViolations ?? [];
  });
  expect(violations).toEqual([]);
});
