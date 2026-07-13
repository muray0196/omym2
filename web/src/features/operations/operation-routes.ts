/**
 * Summary: Maps durable Operation identifiers and API status URLs to SPA recovery routes.
 * Why: Keeps backend remediation inside the accessible polling surface instead of raw JSON.
 */
const API_OPERATION_PREFIX = "/api/operations/";

export function operationRecoveryRoute(operationId: string) {
  return `/operations/${encodeURIComponent(operationId)}`;
}

export function remediationRouteForSpa(route: string) {
  if (!route.startsWith(API_OPERATION_PREFIX)) {
    return route;
  }
  const operationId = route.slice(API_OPERATION_PREFIX.length);
  if (
    operationId.length === 0 ||
    operationId.includes("/") ||
    operationId.includes("?") ||
    operationId.includes("#")
  ) {
    return route;
  }
  return operationRecoveryRoute(operationId);
}
