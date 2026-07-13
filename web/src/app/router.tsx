/**
 * Summary: Declares the frozen route map with explicit route-level lazy imports.
 * Why: Keeps feature chunks statically analyzable and outside the initial shell bundle.
 */
import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "./shell/app-shell";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: AppShell,
    children: [
      { index: true, lazy: () => import("../routes/overview/route") },
      { path: "plans", lazy: () => import("../routes/plans/list-route") },
      {
        path: "plans/new/add",
        lazy: () => import("../routes/plans/new-add-route"),
      },
      {
        path: "plans/new/organize",
        lazy: () => import("../routes/plans/new-organize-route"),
      },
      {
        path: "plans/new/refresh",
        lazy: () => import("../routes/plans/new-refresh-route"),
      },
      {
        path: "plans/:planId",
        lazy: () => import("../routes/plans/detail-route"),
      },
      { path: "library", lazy: () => import("../routes/library/list-route") },
      {
        path: "library/:trackId",
        lazy: () => import("../routes/library/detail-route"),
      },
      { path: "health", lazy: () => import("../routes/health/route") },
      { path: "history", lazy: () => import("../routes/history/list-route") },
      {
        path: "history/:runId",
        lazy: () => import("../routes/history/detail-route"),
      },
      {
        path: "operations/:operationId",
        lazy: () => import("../routes/operations/detail-route"),
      },
      { path: "settings", lazy: () => import("../routes/settings/route") },
      { path: "*", lazy: () => import("../routes/not-found/route") },
    ],
  },
]);
