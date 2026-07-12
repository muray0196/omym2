/**
 * Summary: Verifies editable elements suppress single-character shortcuts.
 * Why: Protects typing and assistive-technology interaction from global commands.
 */
import { describe, expect, it } from "vitest";

import { isEditableTarget } from "./editable-target";

describe("isEditableTarget", () => {
  it.each(["input", "textarea", "select"])(
    "recognizes %s controls",
    (tagName) => {
      expect(isEditableTarget(document.createElement(tagName))).toBe(true);
    },
  );

  it("recognizes contenteditable elements", () => {
    const element = document.createElement("div");
    Object.defineProperty(element, "isContentEditable", { value: true });
    expect(isEditableTarget(element)).toBe(true);
  });

  it("does not classify ordinary elements as editable", () => {
    expect(isEditableTarget(document.createElement("button"))).toBe(false);
  });
});
