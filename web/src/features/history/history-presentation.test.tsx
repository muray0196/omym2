/**
 * Summary: Verifies Run and FileEvent status labels remain explicit and icon-backed.
 * Why: Keeps every coordinated evidence value readable without relying on color alone.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  eventStatusIcon,
  eventStatusPresentation,
  eventTypePresentation,
  runStatusIcon,
  runStatusPresentation,
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

  it("maps every closed FileEvent type", () => {
    for (const [value, label] of [
      ["move_file", "Move file"],
      ["move_lyrics_file", "Move lyrics file"],
      ["move_artwork_file", "Move artwork file"],
      ["move_unprocessed_file", "Move unprocessed file"],
    ] as const) {
      const presentation = eventTypePresentation(value);
      expect(presentation.icon).toBe("info");
      expect(presentation.label).toBe(label);
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).toBe("info");
    }
  });
});
