/**
 * Summary: Tests accessible planning inputs and typed terminal navigation.
 * Why: Proves Add and Refresh create review evidence without exposing file execution.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { BootstrapData, RefreshPlanRequest } from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { Component as AddRoute } from "../../routes/plans/new-add-route";
import { Component as OrganizeRoute } from "../../routes/plans/new-organize-route";
import { Component as RefreshRoute } from "../../routes/plans/new-refresh-route";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import {
  degradedBootstrap,
  normalBootstrap,
  unregisteredBootstrap,
} from "../../test/fixtures/bootstrap";
import {
  CREATED_PLAN_ID,
  completedPlanOperation,
  queuedOperation,
} from "../../test/fixtures/operations";
import { server } from "../../test/server";

describe("planning routes", () => {
  it("starts Add with CSRF, a client UUID, and optional source input", async () => {
    let csrfHeader: string | null = null;
    let idempotencyHeader: string | null = null;
    let receivedBody: unknown;
    server.use(
      http.post("*/api/plans/add", async ({ request }) => {
        csrfHeader = request.headers.get("X-OMYM2-CSRF-Token");
        idempotencyHeader = request.headers.get("Idempotency-Key");
        receivedBody = await request.json();
        return HttpResponse.json(completedPlanOperation(), { status: 200 });
      }),
    );
    const router = renderRoute("/plans/new/add", AddRoute);
    const user = userEvent.setup();

    expect(
      await screen.findByRole("option", {
        name: "/music/library · Registered",
      }),
    ).toBeInTheDocument();
    await user.type(
      screen.getByRole("textbox", { name: /source directory/i }),
      "/music/incoming/favorites ",
    );
    expect(
      screen.getByText(/Library music files are not changed/i),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: /scan and create plan/i }),
    );

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/plans/${CREATED_PLAN_ID}`),
    );
    expect(receivedBody).toEqual({
      library_id: normalBootstrap.data.active_library?.library_id,
      source_path: "/music/incoming/favorites ",
    });
    expect(csrfHeader).toBe(normalBootstrap.data.csrf_token);
    expect(idempotencyHeader).toMatch(/^[0-9a-f-]{36}$/);
  });

  it.each([
    ["an exactly empty source", undefined, null],
    ["a whitespace-only source", "   ", "   "],
  ])(
    "serializes Add with %s by the exact-empty rule",
    async (_, input, expected) => {
      let receivedBody: unknown;
      server.use(
        http.post("*/api/plans/add", async ({ request }) => {
          receivedBody = await request.json();
          return HttpResponse.json(completedPlanOperation(), { status: 200 });
        }),
      );
      renderRoute("/plans/new/add", AddRoute);
      const user = userEvent.setup();

      if (input !== undefined) {
        await user.type(
          screen.getByRole("textbox", { name: /source directory/i }),
          input,
        );
      }
      await user.click(
        screen.getByRole("button", { name: /scan and create plan/i }),
      );

      await waitFor(() =>
        expect(receivedBody).toEqual({
          library_id: normalBootstrap.data.active_library?.library_id,
          source_path: expected,
        }),
      );
    },
  );

  it("keeps the start control disabled while its accepted Operation is active", async () => {
    server.use(
      http.post("*/api/plans/add", () =>
        HttpResponse.json(queuedOperation(), { status: 202 }),
      ),
      http.get("*/api/operations/:operationId", () =>
        HttpResponse.json({
          ...completedPlanOperation(),
          data: {
            ...completedPlanOperation().data,
            completed_at: null,
            progress: {
              completed_units: null,
              message: null,
              stage_code: null,
              total_units: null,
            },
            result: null,
            status: "running",
          },
        }),
      ),
    );
    renderRoute("/plans/new/add", AddRoute);
    const user = userEvent.setup();
    const start = screen.getByRole("button", {
      name: "Scan and create Plan",
    });

    await user.click(start);

    expect(start).toBeDisabled();
    expect(await screen.findByText("Queued")).toBeVisible();
  });

  it("sends an explicit all-target Refresh without a target path", async () => {
    let receivedBody: RefreshPlanRequest | undefined;
    server.use(
      http.post("*/api/plans/refresh", async ({ request }) => {
        receivedBody = (await request.json()) as RefreshPlanRequest;
        return HttpResponse.json(completedPlanOperation("refresh_plan"), {
          status: 200,
        });
      }),
    );
    renderRoute("/plans/new/refresh", RefreshRoute);
    const user = userEvent.setup();

    await user.click(screen.getByRole("radio", { name: /entire library/i }));
    expect(
      screen.queryByRole("textbox", { name: /file or directory path/i }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /create refresh plan/i }),
    );

    await waitFor(() =>
      expect(receivedBody).toEqual({
        library_id: normalBootstrap.data.active_library?.library_id,
        target_kind: "all",
        target_path: null,
      }),
    );
  });

  it("preserves a trailing-space Refresh target path", async () => {
    let receivedBody: RefreshPlanRequest | undefined;
    server.use(
      http.post("*/api/plans/refresh", async ({ request }) => {
        receivedBody = (await request.json()) as RefreshPlanRequest;
        return HttpResponse.json(completedPlanOperation("refresh_plan"), {
          status: 200,
        });
      }),
    );
    renderRoute("/plans/new/refresh", RefreshRoute);
    const user = userEvent.setup();

    await user.type(
      screen.getByRole("textbox", { name: /file or directory path/i }),
      "/music/library/Track.flac ",
    );
    await user.click(
      screen.getByRole("button", { name: /create refresh plan/i }),
    );

    await waitFor(() =>
      expect(receivedBody).toEqual({
        library_id: normalBootstrap.data.active_library?.library_id,
        target_kind: "file",
        target_path: "/music/library/Track.flac ",
      }),
    );
  });

  it("registers an already organized root without inventing a Plan", async () => {
    let receivedBody: unknown;
    server.use(
      http.post("*/api/plans/organize", async ({ request }) => {
        receivedBody = await request.json();
        const completed = completedPlanOperation("organize_plan");
        return HttpResponse.json({
          ...completed,
          data: {
            ...completed.data,
            plan_id: null,
            result: {
              kind: "registered_without_plan",
              library_id: normalBootstrap.data.active_library?.library_id,
              track_count: 12,
            },
          },
        });
      }),
    );
    const router = renderRoute("/plans/new/organize", OrganizeRoute);
    const user = userEvent.setup();

    await user.type(
      screen.getByRole("textbox", { name: /library root/i }),
      "/music/library ",
    );
    await user.click(screen.getByRole("button", { name: /scan library/i }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/library"),
    );
    expect(receivedBody).toEqual({ library_root: "/music/library " });
  });

  it("enables first-run Organize through its explicit backend capability", () => {
    renderRoute(
      "/plans/new/organize",
      OrganizeRoute,
      unregisteredBootstrap.data,
    );

    expect(screen.getByRole("button", { name: /scan library/i })).toBeEnabled();
    expect(
      screen.queryByText("No registered Library is available."),
    ).not.toBeInTheDocument();
  });

  it("shows only explicit Organize capability reasons when disabled", () => {
    renderRoute("/plans/new/organize", OrganizeRoute, degradedBootstrap.data);

    expect(
      screen.getByRole("button", { name: /scan library/i }),
    ).toBeDisabled();
    expect(screen.getByText("Configuration is invalid.")).toBeVisible();
    expect(
      screen.queryByText("No registered Library is available."),
    ).not.toBeInTheDocument();
  });
});

function renderRoute(
  path: string,
  Component: () => React.JSX.Element,
  bootstrap: BootstrapData = normalBootstrap.data,
) {
  const router = createMemoryRouter(
    [
      { path, Component },
      { path: "/plans/:planId", Component: TerminalFixture },
      { path: "/library", Component: TerminalFixture },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <BootstrapContext value={bootstrap}>
        <RouterProvider router={router} />
      </BootstrapContext>
    </QueryClientProvider>,
  );
  return router;
}

function TerminalFixture() {
  return <p>Terminal destination</p>;
}
