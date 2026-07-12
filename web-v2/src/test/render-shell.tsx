/**
 * Summary: Renders the real AppShell with deterministic in-memory route fixtures.
 * Why: Tests navigation behavior without starting a production server or copying API data.
 */
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "../app/shell/app-shell";
import { createQueryClient } from "../app/query-client";
import { RouteHeading } from "../ui/primitives/route-heading";

function OverviewFixture() {
  return <RouteHeading>Operations overview</RouteHeading>;
}

function SettingsFixture() {
  return (
    <>
      <RouteHeading>Settings</RouteHeading>
      <label>
        Draft field
        <input type="text" />
      </label>
    </>
  );
}

export function renderShell(initialEntry = "/") {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: AppShell,
        children: [
          { index: true, Component: OverviewFixture },
          { path: "settings", Component: SettingsFixture },
        ],
      },
    ],
    { initialEntries: [initialEntry] },
  );

  return {
    router,
    user: userEvent.setup(),
    ...render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}
