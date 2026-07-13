/**
 * Summary: Verifies Plan catalog labels remain explicit and resilient to newer server values.
 * Why: Prevents status-only color cues or crashes when the bundled catalog is older than the API.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ActionStatusBadge,
  ActionTypeValue,
  PlanStatusBadge,
  PlanTypeValue,
  ReasonValue,
} from "./plan-presentation";
import {
  actionGroupValueLabel,
  actionGroupingLabel,
  actionStatusIcon,
  actionStatusPresentation,
  actionStatusTone,
  actionTypePresentation,
  actionTypeLabel,
  planStatusIcon,
  planStatusPresentation,
  planStatusTone,
  planTypePresentation,
  planTypeLabel,
  reasonPresentation,
  reasonLabel,
} from "./plan-catalog";

describe("Plan presentation", () => {
  it("renders known Plan and action statuses as visible text", () => {
    const { container } = render(
      <>
        <PlanStatusBadge value="partial_failed" />
        <ActionStatusBadge value="blocked" />
        <PlanTypeValue value="undo" />
        <ActionTypeValue value="move" />
        <ReasonValue value="missing_required_metadata" />
      </>,
    );

    expect(screen.getByText("Partially failed")).toBeVisible();
    expect(screen.getByText("Blocked")).toBeVisible();
    expect(screen.getByText("Undo")).toBeVisible();
    expect(screen.getByText("Move")).toBeVisible();
    expect(screen.getByText("Missing required metadata")).toBeVisible();
    expect(container.querySelectorAll("svg")).toHaveLength(5);
    expect(planStatusIcon("partial_failed")).toBe("warning");
    expect(actionStatusIcon("blocked")).toBe("warning");
  });

  it("falls back to the raw stable value for an unknown server catalog entry", () => {
    render(<PlanStatusBadge value="future_status" />);

    expect(screen.getByText("Unknown status: future_status")).toBeVisible();
    expect(planStatusTone("future_status")).toBe("neutral");
    expect(planStatusIcon("future_status")).toBe("info");
    expect(actionStatusTone("future_status")).toBe("neutral");
    expect(actionStatusIcon("future_status")).toBe("info");
    expect(planStatusPresentation("future_status").meaning).not.toBe("");
    expect(actionStatusPresentation("future_status").meaning).not.toBe("");
  });

  it("maps every known Plan and action status with full presentation data", () => {
    for (const value of [
      "ready",
      "applying",
      "applied",
      "partial_failed",
      "failed",
      "cancelled",
      "expired",
    ]) {
      const presentation = planStatusPresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).not.toBe("");
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
    for (const value of ["planned", "blocked", "applied", "failed"]) {
      const presentation = actionStatusPresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).not.toBe("");
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
  });

  it("labels known type and reason values without using them to enable controls", () => {
    expect(planTypeLabel("refresh")).toBe("Refresh");
    expect(actionTypeLabel("refresh_metadata")).toBe("Refresh metadata");
    expect(reasonLabel("missing_required_metadata")).toBe(
      "Missing required metadata",
    );
    expect(reasonLabel(null)).toBe("—");
  });

  it("maps every known Plan type, action type, and reason with full presentation data", () => {
    for (const [value, label] of [
      ["add", "Add"],
      ["organize", "Organize"],
      ["refresh", "Refresh"],
      ["undo", "Undo"],
    ] as const) {
      const presentation = planTypePresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).toBe(label);
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
    for (const [value, label] of [
      ["move", "Move"],
      ["skip", "Skip"],
      ["refresh_metadata", "Refresh metadata"],
    ] as const) {
      const presentation = actionTypePresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).toBe(label);
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
    for (const value of [
      "target_exists",
      "missing_required_metadata",
      "invalid_path",
      "source_missing",
      "source_changed",
      "duplicate_hash",
      "operation_interrupted",
    ]) {
      const presentation = reasonPresentation(value);
      expect(presentation.icon).toBe("warning");
      expect(presentation.meaning).not.toBe("");
    }
  });

  it("uses neutral info presentation for unknown Plan catalog values", () => {
    expect(planTypePresentation("future_type")).toMatchObject({
      icon: "info",
      label: "Unknown type: future_type",
      tone: "neutral",
    });
    expect(actionTypePresentation("future_action")).toMatchObject({
      icon: "info",
      label: "Unknown action type: future_action",
      tone: "neutral",
    });
    expect(reasonPresentation("future_reason")).toMatchObject({
      icon: "info",
      label: "Unknown reason: future_reason",
      tone: "neutral",
    });
  });

  it("labels each selectable grouping without assuming an opaque group key", () => {
    expect(actionGroupingLabel("target_directory")).toBe("Target directory");
    expect(actionGroupingLabel("future_grouping")).toBe(
      "Unknown grouping: future_grouping",
    );
  });

  it("maps catalog-backed group values and preserves non-catalog server labels", () => {
    expect(actionGroupValueLabel("status", "blocked", "Server status")).toBe(
      "Blocked",
    );
    expect(actionGroupValueLabel("action_type", "move", "Server type")).toBe(
      "Move",
    );
    expect(
      actionGroupValueLabel("block_reason", "target_exists", "Server reason"),
    ).toBe("Target already exists");
    expect(
      actionGroupValueLabel("status", "future_status", "Server future"),
    ).toBe("Unknown status: future_status");
    expect(
      actionGroupValueLabel(
        "target_directory",
        "opaque-key",
        "Server directory",
      ),
    ).toBe("Server directory");
  });
});
