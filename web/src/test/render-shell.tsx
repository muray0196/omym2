/**
 * Summary: Renders the real AppShell with deterministic in-memory route fixtures.
 * Why: Tests navigation behavior without starting a production server or copying API data.
 */
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import {
  createMemoryRouter,
  Link,
  RouterProvider,
  useParams,
} from "react-router-dom";

import { AppShell } from "../app/shell/app-shell";
import { createQueryClient } from "../app/query-client";
import { Button } from "../ui/primitives/button";
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

function KeyboardListFixture() {
  const [invocations, setInvocations] = useState(0);

  return (
    <>
      <RouteHeading>Keyboard list</RouteHeading>
      <label>
        Search
        <input data-list-search type="search" />
      </label>
      <ul>
        <li>
          <Link data-list-item to="/detail/first">
            First detail
          </Link>
        </li>
        <li>
          <Link data-list-item to="/detail/second">
            Second detail
          </Link>
        </li>
      </ul>
      <Button
        onClick={() => setInvocations((current) => current + 1)}
        variant="primary"
      >
        Invoke primary
      </Button>
      <p>Primary invocations: {invocations}</p>
    </>
  );
}

function KeyboardDetailFixture() {
  const { itemId = "" } = useParams();
  const nextItemId = itemId === "first" ? "second" : "first";

  return (
    <>
      <Link data-detail-back to="/list">
        Back to list
      </Link>
      <RouteHeading>Keyboard detail</RouteHeading>
      <p>Detail ID: {itemId}</p>
      <Link to={`/detail/${nextItemId}`}>Open next detail</Link>
      <Link to="?view=evidence">Update detail query</Link>
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
          { path: "list", Component: KeyboardListFixture },
          { path: "detail/:itemId", Component: KeyboardDetailFixture },
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
