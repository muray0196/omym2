/**
 * Summary: Extends Playwright with an automatic loopback-only request guard.
 * Why: Makes every browser journey fail if runtime code reaches a remote host.
 */
import { expect, test as base, type Route } from "@playwright/test";

const GUARDED_NETWORK_PROTOCOLS = new Set(["http:", "https:", "ws:", "wss:"]);
const LOOPBACK_HOSTNAMES = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

interface RequestGuardFixtures {
  loopbackRequestGuard: void;
}

export const test = base.extend<RequestGuardFixtures>({
  loopbackRequestGuard: [
    async ({ context }, use) => {
      const blockedUrls: string[] = [];
      const guard = async (route: Route) => {
        const requestUrl = new URL(route.request().url());
        if (
          GUARDED_NETWORK_PROTOCOLS.has(requestUrl.protocol) &&
          !LOOPBACK_HOSTNAMES.has(requestUrl.hostname)
        ) {
          blockedUrls.push(requestUrl.href);
          await route.abort("blockedbyclient");
          return;
        }
        await route.continue();
      };
      await context.route("**/*", guard);
      await use();
      await context.unroute("**/*", guard);
      expect(
        blockedUrls,
        "Browser runtime requests must stay on a loopback host.",
      ).toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
