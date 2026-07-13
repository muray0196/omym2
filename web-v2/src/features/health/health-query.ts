/**
 * Summary: Defines generated-SDK queries for persisted Check issues, facets, and groups.
 * Why: Keeps Health read-only, deduplicated, and opaque-cursor safe.
 */
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getCheckIssueFacets,
  getCheckIssueGroups,
  getCheckIssues,
  type ApiFailureEnvelope,
  type CheckIssueFacetsData,
  type CheckIssueGroupsData,
  type CheckIssuesData,
} from "../../api/generated";
import {
  InspectionUnexpectedDataError,
  throwInspectionResponseError,
} from "../inspection/query-errors";
import type { HealthFilters } from "./health-url-state";

const SURFACE = "Health";

export function checkIssuesInfiniteQuery(filters: HealthFilters) {
  return infiniteQueryOptions({
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: CheckIssuesData) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<CheckIssuesData> =>
      readIssues(filters, pageParam),
    queryKey: [
      "check",
      filters.query,
      filters.issueType ?? null,
      filters.libraryId,
      filters.groupBy,
      filters.groupKey ?? null,
    ] as const,
  });
}

export function checkIssueFacetsQuery(filters: HealthFilters) {
  return queryOptions({
    queryFn: () => readFacets(filters),
    queryKey: ["check", "facets", filters.query, filters.libraryId] as const,
  });
}

export function checkIssueGroupsInfiniteQuery(filters: HealthFilters) {
  return infiniteQueryOptions({
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: CheckIssueGroupsData) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<CheckIssueGroupsData> =>
      readGroups(filters, pageParam),
    queryKey: [
      "check",
      "groups",
      filters.groupBy,
      filters.query,
      filters.issueType ?? null,
      filters.libraryId,
    ] as const,
  });
}

async function readIssues(
  filters: HealthFilters,
  cursor?: string,
): Promise<CheckIssuesData> {
  const response = await getCheckIssues({
    baseUrl: location.origin,
    query: {
      cursor,
      group_by: filters.groupKey === undefined ? undefined : filters.groupBy,
      group_key: filters.groupKey,
      issue_type: filters.issueType,
      library_id: filters.libraryId || undefined,
      query: filters.query || undefined,
    },
  });
  return dataOrThrow(response, "findings");
}

async function readFacets(
  filters: HealthFilters,
): Promise<CheckIssueFacetsData> {
  const response = await getCheckIssueFacets({
    baseUrl: location.origin,
    query: {
      library_id: filters.libraryId || undefined,
      query: filters.query || undefined,
    },
  });
  return dataOrThrow(response, "facets");
}

async function readGroups(
  filters: HealthFilters,
  cursor?: string,
): Promise<CheckIssueGroupsData> {
  const response = await getCheckIssueGroups({
    baseUrl: location.origin,
    query: {
      cursor,
      group_by: filters.groupBy,
      issue_type: filters.issueType,
      library_id: filters.libraryId || undefined,
      query: filters.query || undefined,
    },
  });
  return dataOrThrow(response, "groups");
}

function dataOrThrow<Data>(
  response: {
    data?: { data: Data | null };
    error?: ApiFailureEnvelope;
    response?: Response;
  },
  label: string,
): Data {
  if (response.error !== undefined)
    throwInspectionResponseError(
      `${SURFACE} ${label}`,
      response.error,
      response.response,
    );
  const data = response.data?.data;
  if (data == null)
    throw new InspectionUnexpectedDataError(`${SURFACE} ${label}`);
  return data;
}
