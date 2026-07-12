/**
 * Summary: Verifies deterministic local Command Center filtering.
 * Why: Protects navigation search without relying on unavailable backend records.
 */
import { describe, expect, it } from "vitest";

import { filterCommands } from "./command-sources";

describe("filterCommands", () => {
  it("returns frozen navigation order for an empty query", () => {
    expect(filterCommands("").map((item) => item.label)).toEqual([
      "Overview",
      "Plans",
      "Library",
      "Health",
      "History",
      "Settings",
    ]);
  });

  it("matches labels without case sensitivity", () => {
    expect(filterCommands("SETTINGS").map((item) => item.to)).toEqual([
      "/settings",
    ]);
  });

  it("returns an empty result for an unknown command", () => {
    expect(filterCommands("play music")).toEqual([]);
  });
});
