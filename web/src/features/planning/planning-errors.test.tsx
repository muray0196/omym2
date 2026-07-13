/**
 * Summary: Verifies accessible planning mutation diagnostics and Operation remediation.
 * Why: Keeps typed start failures focusable without leaving the SPA recovery surface.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ApiFailureEnvelope } from "../../api/generated";
import { OPERATION_ID } from "../../test/fixtures/operations";
import { OperationApiError } from "../operations/operation-start";
import { PlanningMutationError } from "./planning-errors";

describe("PlanningMutationError", () => {
  it("focuses the summary, links the affected field, and translates Operation remediation", async () => {
    const user = userEvent.setup();
    const failure = {
      data: null,
      errors: [
        {
          code: "operation_in_progress",
          field: "body.target_path",
          message: "Another Operation is already active.",
          remediation: {
            command: "omym2 check",
            label: "View active Operation",
            route: `/api/operations/${OPERATION_ID}`,
          },
          retryable: true,
        },
      ],
    } satisfies ApiFailureEnvelope;
    render(
      <MemoryRouter>
        <label htmlFor="refresh-target">Refresh target</label>
        <input id="refresh-target" />
        <PlanningMutationError error={new OperationApiError(failure, 409)} />
      </MemoryRouter>,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveFocus();
    expect(screen.getByText("omym2 check")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "View active Operation" }),
    ).toHaveAttribute("href", `/operations/${OPERATION_ID}`);

    await user.click(
      screen.getByRole("link", {
        name: "Another Operation is already active.",
      }),
    );
    expect(screen.getByLabelText("Refresh target")).toHaveFocus();
  });
});
