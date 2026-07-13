/**
 * Summary: Configures Chromium end-to-end checks against a real loopback server.
 * Why: Exercises keyboard and accessibility behavior without a mocked browser API.
 */
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.OMYM2_E2E_BASE_URL ?? "http://127.0.0.1:8765";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    colorScheme: "dark",
    locale: "en-US",
    timezoneId: "UTC",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
