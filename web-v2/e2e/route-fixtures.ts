/**
 * Summary: Centralizes deterministic M2 browser route fixtures.
 * Why: Keeps inspection deep links, accessibility, and the pre-M4 mutation gate aligned.
 */
export const allM2RoutePaths = [
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

export const deepPlanRoute = allM2RoutePaths[5];
export const notFoundRoute = "/missing-renewal-route";
