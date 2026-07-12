/**
 * Summary: Centralizes deterministic M1 browser route fixtures.
 * Why: Keeps deep-link, accessibility, and mutation gates aligned with the frozen route map.
 */
export const allM1RoutePaths = [
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

export const deepPlanRoute = allM1RoutePaths[5];
export const notFoundRoute = "/missing-renewal-route";
