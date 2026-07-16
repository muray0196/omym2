/**
 * Summary: Verifies exhaustive Plan catalog labels and explicit failures for invalid values.
 * Why: Prevents status-only color cues or silent presentation of corrupted enum data.
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
  actionTypePresentation,
  actionTypeLabel,
  planStatusIcon,
  planStatusPresentation,
  planTypePresentation,
  planTypeLabel,
  reasonPresentation,
  reasonLabel,
} from "./plan-catalog";
import { planCopy } from "./plan-copy";

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

  it("rejects an unknown server catalog entry", () => {
    expect(() => planStatusPresentation("future_status")).toThrow(
      "Unknown Plan status value: future_status",
    );
    expect(() => actionStatusPresentation("future_status")).toThrow(
      "Unknown PlanAction status value: future_status",
    );
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
      ["move_lyrics", "Move lyrics"],
      ["move_artwork", "Move artwork"],
      ["move_unprocessed", "Move unprocessed file"],
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
      "companion_owner_blocked",
      "companion_association_ambiguous",
      "companion_dependency_failed",
      "operation_interrupted",
    ]) {
      const presentation = reasonPresentation(value);
      expect(presentation.icon).toBe("warning");
      expect(presentation.meaning).not.toBe("");
    }
    expect(planCopy.artistNames.issue.automatic_lookup_disabled).toBe(
      "Automatic lookup disabled",
    );
  });

  it("rejects invalid Plan catalog values", () => {
    expect(() => planTypePresentation("future_type")).toThrow(
      "Unknown Plan type value: future_type",
    );
    expect(() => actionTypePresentation("future_action")).toThrow(
      "Unknown PlanAction type value: future_action",
    );
    expect(() => reasonPresentation("future_reason")).toThrow(
      "Unknown PlanAction reason value: future_reason",
    );
  });

  it("labels each selectable grouping without assuming an opaque group key", () => {
    expect(actionGroupingLabel("target_directory")).toBe("Target directory");
    expect(() => actionGroupingLabel("future_grouping")).toThrow(
      "Unknown PlanAction grouping value: future_grouping",
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
    expect(() =>
      actionGroupValueLabel("status", "future_status", "Server future"),
    ).toThrow("Unknown PlanAction status value: future_status");
    expect(
      actionGroupValueLabel(
        "target_directory",
        "opaque-key",
        "Server directory",
      ),
    ).toBe("Server directory");
  });
});
