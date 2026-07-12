/**
 * Summary: Verifies observable normal, degraded, and disconnected Bootstrap presentation.
 * Why: Protects recovery access while the local backend is partially unavailable.
 */
import { http, HttpResponse } from "msw";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ApiFailureEnvelope } from "../../api/generated";
import { renderShell } from "../../test/render-shell";
import {
  degradedBootstrap,
  unregisteredBootstrap,
} from "../../test/fixtures/bootstrap";
import { server } from "../../test/server";

describe("BootstrapBoundary", () => {
  it("shows the active Library for a normal Bootstrap response", async () => {
    renderShell();

    expect(await screen.findByText("Local service connected")).toBeVisible();
    expect(screen.getByText("/music/library")).toBeVisible();
  });

  it("keeps Settings recovery available with degraded data and top-level errors", async () => {
    server.use(
      http.get("*/api/bootstrap", () => HttpResponse.json(degradedBootstrap)),
    );
    renderShell();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("OMYM2 needs attention");
    expect(
      screen.getByRole("link", { name: "Review Settings" }),
    ).toHaveAttribute("href", "/settings");
  });

  it("displays the backend remediation for an unregistered Library", async () => {
    server.use(
      http.get("*/api/bootstrap", () =>
        HttpResponse.json(unregisteredBootstrap),
      ),
    );
    renderShell();

    expect(
      await screen.findByRole("link", { name: "Create an Organize Plan" }),
    ).toHaveAttribute("href", "/plans/new/organize");
    expect(
      screen.queryByRole("link", { name: "Open Settings" }),
    ).not.toBeInTheDocument();
  });

  it("presents a typed server failure separately from disconnection", async () => {
    const failure = {
      data: null,
      errors: [
        {
          code: "internal_error",
          message: "The startup snapshot could not be loaded.",
          retryable: true,
          remediation: {
            command: "omym2 check",
            label: "Inspect from the CLI",
          },
        },
      ],
    } satisfies ApiFailureEnvelope;
    server.use(
      http.get("*/api/bootstrap", () =>
        HttpResponse.json(failure, { status: 500 }),
      ),
    );
    renderShell();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not load its startup state");
    expect(alert).toHaveTextContent("startup snapshot could not be loaded");
    expect(alert).toHaveTextContent("Inspect from the CLI");
    expect(alert).toHaveTextContent("omym2 check");
    expect(alert).not.toHaveTextContent("service is unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  it("offers an explicit retry after a transport failure", async () => {
    server.use(http.get("*/api/bootstrap", () => HttpResponse.error()));
    renderShell();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("local OMYM2 service is unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
