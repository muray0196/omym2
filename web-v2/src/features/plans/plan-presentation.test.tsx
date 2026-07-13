/**
 * Summary: Verifies Plan catalog labels remain explicit and resilient to newer server values.
 * Why: Prevents status-only color cues or crashes when the bundled catalog is older than the API.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionStatusBadge, PlanStatusBadge } from "./plan-presentation";
import {
  actionGroupingLabel,
  actionTypeLabel,
  planTypeLabel,
  reasonLabel,
} from "./plan-catalog";

describe("Plan presentation", () => {
  it("renders known Plan and action statuses as visible text", () => {
    render(
      <>
        <PlanStatusBadge value="partial_failed" />
        <ActionStatusBadge value="blocked" />
      </>,
    );

    expect(screen.getByText("Partially failed")).toBeVisible();
    expect(screen.getByText("Blocked")).toBeVisible();
  });

  it("falls back to the raw stable value for an unknown server catalog entry", () => {
    render(<PlanStatusBadge value="future_status" />);

    expect(screen.getByText("Unknown status: future_status")).toBeVisible();
  });

  it("labels known type and reason values without using them to enable controls", () => {
    expect(planTypeLabel("refresh")).toBe("Refresh");
    expect(actionTypeLabel("refresh_metadata")).toBe("Refresh metadata");
    expect(reasonLabel("missing_required_metadata")).toBe(
      "Missing required metadata",
    );
    expect(reasonLabel(null)).toBe("—");
  });

  it("labels each selectable grouping without assuming an opaque group key", () => {
    expect(actionGroupingLabel("target_directory")).toBe("Target directory");
    expect(actionGroupingLabel("future_grouping")).toBe(
      "Unknown grouping: future_grouping",
    );
  });
});
