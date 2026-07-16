/**
 * Summary: Configures bundled frontend unit and component tests.
 * Why: Makes accessibility-focused browser behavior deterministic under jsdom and MSW.
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    clearMocks: true,
    // Full-form userEvent tests legitimately exceed the 5s default on
    // loaded CI runners; the suite still finishes in well under a minute.
    testTimeout: 15_000,
  },
});
