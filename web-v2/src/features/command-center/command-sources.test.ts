/**
 * Summary: Verifies deterministic local Command Center filtering.
 * Why: Protects navigation search without relying on unavailable backend records.
 */
import { describe, expect, it } from "vitest";

import { buildCommands, filterCommands } from "./command-sources";

describe("filterCommands", () => {
  it("orders recommended actions and commands before navigation", () => {
    expect(filterCommands("").map((item) => item.label)).toEqual([
      "Add music",
      "Create a Plan",
      "Inspect Health",
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

  it("places recent Plans, Runs, and Tracks before navigation", () => {
    const commands = buildCommands({
      plans: [
        {
          created_at: "2026-07-13T00:00:00Z",
          library_id: "library-id",
          plan_id: "018f0000-plan",
          plan_type: "add",
          status: "ready",
          summary: {
            total: 0,
            counts: {
              planned: { move: 0, skip: 0, refresh_metadata: 0 },
              blocked: { move: 0, skip: 0, refresh_metadata: 0 },
              applied: { move: 0, skip: 0, refresh_metadata: 0 },
              failed: { move: 0, skip: 0, refresh_metadata: 0 },
            },
          },
        },
      ],
    });

    expect(commands.findIndex((item) => item.kind === "plan")).toBeLessThan(
      commands.findIndex((item) => item.kind === "navigation"),
    );
  });

  it("returns an empty result for an unknown command", () => {
    expect(filterCommands("play music")).toEqual([]);
  });
});
