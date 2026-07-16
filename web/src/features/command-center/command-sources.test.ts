/**
 * Summary: Verifies deterministic local Command Center filtering.
 * Why: Protects navigation search without relying on unavailable backend records.
 */
import { describe, expect, it } from "vitest";

import type { PlanSummary, RunHeader } from "../../api/generated";
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
              planned: {
                move: 0,
                move_artwork: 0,
                move_lyrics: 0,
                move_unprocessed: 0,
                skip: 0,
                refresh_metadata: 0,
              },
              blocked: {
                move: 0,
                move_artwork: 0,
                move_lyrics: 0,
                move_unprocessed: 0,
                skip: 0,
                refresh_metadata: 0,
              },
              applied: {
                move: 0,
                move_artwork: 0,
                move_lyrics: 0,
                move_unprocessed: 0,
                skip: 0,
                refresh_metadata: 0,
              },
              failed: {
                move: 0,
                move_artwork: 0,
                move_lyrics: 0,
                move_unprocessed: 0,
                skip: 0,
                refresh_metadata: 0,
              },
            },
          },
        },
      ],
    });

    expect(commands.findIndex((item) => item.kind === "plan")).toBeLessThan(
      commands.findIndex((item) => item.kind === "navigation"),
    );
  });

  it("uses catalog labels for known and unknown Plan and Run statuses", () => {
    const commands = buildCommands({
      plans: [
        planWithStatus("018f1000-plan", "partial_failed"),
        planWithStatus("018f2000-plan", "future_plan_status"),
      ],
      runs: [
        runWithStatus("018f3000-run", "partial_failed"),
        runWithStatus("018f4000-run", "future_run_status"),
      ],
    });

    expect(
      commands.filter((item) => item.kind === "plan").map((item) => item.label),
    ).toEqual([
      "Plan 018f1000 · Partially failed",
      "Plan 018f2000 · Unknown status: future_plan_status",
    ]);
    expect(
      commands.filter((item) => item.kind === "run").map((item) => item.label),
    ).toEqual([
      "Run 018f3000 · Partially failed",
      "Run 018f4000 · Unknown status: future_run_status",
    ]);
  });

  it("returns an empty result for an unknown command", () => {
    expect(filterCommands("play music")).toEqual([]);
  });
});

function planWithStatus(planId: string, status: string): PlanSummary {
  return {
    created_at: "2026-07-13T00:00:00Z",
    library_id: "library-id",
    plan_id: planId,
    plan_type: "add",
    status,
    summary: {
      total: 0,
      counts: {
        planned: {
          move: 0,
          move_artwork: 0,
          move_lyrics: 0,
          move_unprocessed: 0,
          skip: 0,
          refresh_metadata: 0,
        },
        blocked: {
          move: 0,
          move_artwork: 0,
          move_lyrics: 0,
          move_unprocessed: 0,
          skip: 0,
          refresh_metadata: 0,
        },
        applied: {
          move: 0,
          move_artwork: 0,
          move_lyrics: 0,
          move_unprocessed: 0,
          skip: 0,
          refresh_metadata: 0,
        },
        failed: {
          move: 0,
          move_artwork: 0,
          move_lyrics: 0,
          move_unprocessed: 0,
          skip: 0,
          refresh_metadata: 0,
        },
      },
    },
  } as unknown as PlanSummary;
}

function runWithStatus(runId: string, status: string): RunHeader {
  return {
    completed_at: "2026-07-13T00:00:01Z",
    error_summary: null,
    library_id: "library-id",
    plan_id: "plan-id",
    run_id: runId,
    started_at: "2026-07-13T00:00:00Z",
    status,
  } as unknown as RunHeader;
}
