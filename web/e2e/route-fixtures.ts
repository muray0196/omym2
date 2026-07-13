/**
 * Summary: Centralizes deterministic M3 browser route fixtures.
 * Why: Keeps inspection deep links, accessibility, and passive-route checks aligned.
 */
export const allM3RoutePaths = [
  "/",
  "/plans",
  "/plans/new/add",
  "/plans/new/organize",
  "/plans/new/refresh",
  "/plans/018f0000-0000-7000-8000-000000000010",
  "/library",
  "/library/018f0000-0000-7000-8000-000000000020",
  "/health",
  "/history",
  "/history/018f0000-0000-7000-8000-000000000030",
  "/settings",
] as const;

export const deepPlanRoute = allM3RoutePaths[5];
export const operationRecoveryRoute =
  "/operations/018f0000-0000-7000-8000-000000000040";
export const notFoundRoute = "/missing-route";
