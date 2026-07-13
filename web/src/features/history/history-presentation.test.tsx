/**
 * Summary: Verifies Run and FileEvent status labels remain explicit and icon-backed.
 * Why: Keeps known and future evidence readable without relying on color alone.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  eventStatusIcon,
  eventStatusPresentation,
  eventStatusTone,
  eventTypePresentation,
  runStatusIcon,
  runStatusPresentation,
  runStatusTone,
} from "./history-catalog";
import {
  EventStatusBadge,
  EventTypeValue,
  RunStatusBadge,
} from "./history-presentation";

describe("History presentation", () => {
  it("renders known Run and FileEvent statuses as text with icons", () => {
    const { container } = render(
      <>
        <RunStatusBadge value="partial_failed" />
        <EventStatusBadge value="succeeded" />
        <EventTypeValue value="move_file" />
      </>,
    );

    expect(screen.getByText("Partially failed")).toBeVisible();
    expect(screen.getByText("Succeeded")).toBeVisible();
    expect(screen.getByText("Move file")).toBeVisible();
    expect(container.querySelectorAll("svg")).toHaveLength(3);
    expect(runStatusIcon("partial_failed")).toBe("warning");
    expect(eventStatusIcon("succeeded")).toBe("check");
  });

  it("uses a neutral info fallback for unknown Run and FileEvent statuses", () => {
    const { container } = render(
      <>
        <RunStatusBadge value="future_run_status" />
        <EventStatusBadge value="future_event_status" />
      </>,
    );

    expect(screen.getByText("Unknown status: future_run_status")).toBeVisible();
    expect(
      screen.getByText("Unknown status: future_event_status"),
    ).toBeVisible();
    expect(container.querySelectorAll("svg")).toHaveLength(2);
    expect(runStatusTone("future_run_status")).toBe("neutral");
    expect(runStatusIcon("future_run_status")).toBe("info");
    expect(eventStatusTone("future_event_status")).toBe("neutral");
    expect(eventStatusIcon("future_event_status")).toBe("info");
    expect(runStatusPresentation("future_run_status").meaning).not.toBe("");
    expect(eventStatusPresentation("future_event_status").meaning).not.toBe("");
  });

  it("maps every known Run and FileEvent status with full presentation data", () => {
    for (const value of ["running", "succeeded", "partial_failed", "failed"]) {
      const presentation = runStatusPresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).not.toBe("");
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
    for (const value of ["pending", "succeeded", "failed"]) {
      const presentation = eventStatusPresentation(value);
      expect(presentation.icon).not.toBe("");
      expect(presentation.label).not.toBe("");
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).not.toBe("");
    }
  });

  it("maps the closed FileEvent type and preserves an unknown raw code", () => {
    expect(eventTypePresentation("move_file")).toEqual({
      icon: "info",
      label: "Move file",
      meaning: "Records one attempted Library music file move.",
      tone: "info",
    });
    expect(eventTypePresentation("future_event_type")).toMatchObject({
      icon: "info",
      label: "Unknown event type: future_event_type",
      tone: "neutral",
    });
  });
});
