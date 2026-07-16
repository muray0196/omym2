/**
 * Summary: Verifies Library and Track status labels remain explicit and icon-backed.
 * Why: Keeps every coordinated readiness and inventory value explicit.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  libraryStatusIcon,
  libraryStatusPresentation,
  trackStatusIcon,
  trackStatusPresentation,
} from "./library-catalog";
import { LibraryStatusBadge, TrackStatusBadge } from "./library-presentation";

describe("Library presentation", () => {
  it("renders known Library and Track statuses as text with icons", () => {
    const { container } = render(
      <>
        <LibraryStatusBadge value="registered" />
        <TrackStatusBadge value="removed" />
      </>,
    );

    expect(screen.getByText("Registered")).toBeVisible();
    expect(screen.getByText("Removed")).toBeVisible();
    expect(container.querySelectorAll("svg")).toHaveLength(2);
    expect(libraryStatusIcon("registered")).toBe("check");
    expect(trackStatusIcon("removed")).toBe("close");
  });

  it("maps every known Library and Track status with full presentation data", () => {
    for (const [value, tone, icon] of [
      ["registered", "success", "check"],
      ["unregistered", "neutral", "info"],
      ["stale", "warning", "warning"],
      ["blocked", "warning", "warning"],
    ] as const) {
      const presentation = libraryStatusPresentation(value);
      expect(presentation.icon).toBe(icon);
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).toBe(tone);
    }
    for (const [value, tone, icon] of [
      ["active", "success", "check"],
      ["removed", "neutral", "close"],
    ] as const) {
      const presentation = trackStatusPresentation(value);
      expect(presentation.icon).toBe(icon);
      expect(presentation.meaning).not.toBe("");
      expect(presentation.tone).toBe(tone);
    }
  });
});
