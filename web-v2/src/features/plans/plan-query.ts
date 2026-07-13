/**
 * Summary: Defines generated-SDK read queries for Plan inspection and opaque cursor pages.
 * Why: Keeps Plan browse data deduplicated, typed, and separate from any mutation transport.
 */
import {
  infiniteQueryOptions,
  queryOptions,
  type InfiniteData,
} from "@tanstack/react-query";

import {
  getPlan,
  getPlanActionFacets,
  groupPlanActions,
  listPlanActions,
  listPlans,
  type ApiFailureEnvelope,
  type PaginatedDataPlanActionResource,
  type PaginatedDataPlanSummary,
  type PlanDetailData,
  type PlanActionFacetsData,
  type PlanActionGroupsData,
  type PlanActionResource,
  type PlanSummary as GeneratedPlanSummary,
} from "../../api/generated";
import type { PlanActionFilters, PlanListFilters } from "./plan-url-state";

export type PlanSummary = GeneratedPlanSummary;
export type PlanAction = PlanActionResource;
export type PlanActionPage = PaginatedDataPlanActionResource;
export type PlanActionFacets = PlanActionFacetsData;
export type PlanActionGroups = PlanActionGroupsData;
export type PlanDetail = PlanDetailData;

export class PlansApiError extends Error {
  readonly envelope: ApiFailureEnvelope;

  constructor(envelope: ApiFailureEnvelope) {
    super("Plan inspection returned a typed API failure.");
    this.name = "PlansApiError";
    this.envelope = envelope;
  }
}

export class PlansTransportError extends Error {
  constructor() {
    super("Plan inspection could not reach the local service.");
    this.name = "PlansTransportError";
  }
}

export class PlansUnexpectedDataError extends Error {
  constructor() {
    super("Plan inspection returned no readable data.");
    this.name = "PlansUnexpectedDataError";
  }
}

export function plansInfiniteQuery(filters: PlanListFilters) {
  return infiniteQueryOptions<
    PaginatedDataPlanSummary,
    Error,
    InfiniteData<PaginatedDataPlanSummary, string | undefined>,
    readonly unknown[],
    string | undefined
  >({
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }) => readPlansPage(filters, pageParam),
    queryKey: [
      "plans",
      filters.query,
      filters.status ?? null,
      filters.type ?? null,
      filters.blocked,
    ] as const,
  });
}

export function exactPlanQuery(planId: string) {
  return queryOptions({
    enabled: planId.length > 0,
    queryFn: () => readPlanDetail(planId),
    queryKey: ["plans", planId, "detail"] as const,
  });
}

export function exactPlanListQuery(planId: string) {
  return queryOptions({
    enabled: planId.length > 0,
    queryFn: () => readExactPlanPage(planId),
    queryKey: ["plans", "exact", planId] as const,
  });
}

export function planActionsInfiniteQuery(
  planId: string,
  filters: PlanActionFilters,
) {
  return infiniteQueryOptions<
    PaginatedDataPlanActionResource,
    Error,
    InfiniteData<PaginatedDataPlanActionResource, string | undefined>,
    readonly unknown[],
    string | undefined
  >({
    enabled: planId.length > 0,
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }) => readPlanActionsPage(planId, filters, pageParam),
    queryKey: [
      "plans",
      planId,
      "actions",
      filters.query,
      filters.status ?? null,
      filters.actionType ?? null,
      filters.reason ?? null,
      filters.groupBy,
      filters.groupKey ?? null,
    ] as const,
  });
}

export function planActionFacetsQuery(
  planId: string,
  filters: PlanActionFilters,
) {
  return queryOptions({
    enabled: planId.length > 0,
    queryFn: () => readPlanActionFacets(planId, filters),
    queryKey: [
      "plans",
      planId,
      "facets",
      filters.query,
      filters.status ?? null,
      filters.actionType ?? null,
      filters.reason ?? null,
    ] as const,
  });
}

export function planActionGroupsInfiniteQuery(
  planId: string,
  filters: PlanActionFilters,
) {
  return infiniteQueryOptions<
    PlanActionGroupsData,
    Error,
    InfiniteData<PlanActionGroupsData, string | undefined>,
    readonly unknown[],
    string | undefined
  >({
    enabled: planId.length > 0,
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }) =>
      readPlanActionGroupsPage(planId, filters, pageParam),
    queryKey: [
      "plans",
      planId,
      "groups",
      filters.groupBy,
      filters.query,
      filters.status ?? null,
      filters.actionType ?? null,
      filters.reason ?? null,
    ] as const,
  });
}

export function planActionGroupsQuery(
  planId: string,
  filters: PlanActionFilters,
) {
  return queryOptions({
    enabled: planId.length > 0,
    queryFn: () => readPlanActionGroupsPage(planId, filters, undefined),
    queryKey: [
      "plans",
      planId,
      "groups",
      filters.groupBy,
      filters.query,
      filters.status ?? null,
      filters.actionType ?? null,
      filters.reason ?? null,
    ] as const,
  });
}

async function readPlansPage(
  filters: PlanListFilters,
  cursor: string | undefined,
): Promise<PaginatedDataPlanSummary> {
  const response = await listPlans({
    baseUrl: globalThis.location.origin,
    query: {
      blocked: filters.blocked || undefined,
      cursor,
      query: filters.query.length === 0 ? undefined : filters.query,
      status: filters.status,
      type: filters.type,
    },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

async function readPlanDetail(planId: string): Promise<PlanDetailData> {
  const response = await getPlan({
    baseUrl: globalThis.location.origin,
    path: { plan_id: planId },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

async function readExactPlanPage(
  planId: string,
): Promise<PaginatedDataPlanSummary> {
  const response = await listPlans({
    baseUrl: globalThis.location.origin,
    query: { query: planId },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

async function readPlanActionsPage(
  planId: string,
  filters: PlanActionFilters,
  cursor: string | undefined,
): Promise<PaginatedDataPlanActionResource> {
  const response = await listPlanActions({
    baseUrl: globalThis.location.origin,
    path: { plan_id: planId },
    query: {
      action_type: filters.actionType,
      cursor,
      group_by: filters.groupKey === undefined ? undefined : filters.groupBy,
      group_key: filters.groupKey,
      query: filters.query.length === 0 ? undefined : filters.query,
      reason: filters.reason,
      status: filters.status,
    },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

async function readPlanActionFacets(
  planId: string,
  filters: PlanActionFilters,
): Promise<PlanActionFacetsData> {
  const response = await getPlanActionFacets({
    baseUrl: globalThis.location.origin,
    path: { plan_id: planId },
    query: {
      action_type: filters.actionType,
      query: filters.query.length === 0 ? undefined : filters.query,
      reason: filters.reason,
      status: filters.status,
    },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

async function readPlanActionGroupsPage(
  planId: string,
  filters: PlanActionFilters,
  cursor: string | undefined,
): Promise<PlanActionGroupsData> {
  const response = await groupPlanActions({
    baseUrl: globalThis.location.origin,
    path: { plan_id: planId },
    query: {
      action_type: filters.actionType,
      cursor,
      group_by: filters.groupBy,
      query: filters.query.length === 0 ? undefined : filters.query,
      reason: filters.reason,
      status: filters.status,
    },
  });

  if (response.error !== undefined) {
    throwPlanResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new PlansUnexpectedDataError();
  }
  return response.data.data;
}

function throwPlanResponseError(
  envelope: ApiFailureEnvelope,
  response: Response | undefined,
): never {
  if (response === undefined) {
    throw new PlansTransportError();
  }
  throw new PlansApiError(envelope);
}
