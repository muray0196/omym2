/**
 * Summary: Installs deterministic DOM, dialog, cleanup, and MSW test behavior.
 * Why: Keeps component tests browser-like without adding runtime shims.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});

Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.open = true;
    },
  },
  close: {
    configurable: true,
    value(this: HTMLDialogElement) {
      if (!this.open) {
        return;
      }
      this.open = false;
      this.dispatchEvent(new Event("close"));
    },
  },
});
