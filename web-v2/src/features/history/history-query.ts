/**
 * Summary: Defines generated-SDK queries for Run and FileEvent evidence.
 * Why: Deduplicates read-only server state while passing opaque cursors unchanged.
 */
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getHistory,
  getHistoryFacets,
  getRun,
  getRunEventFacets,
  getRunEventGroups,
  getRunEvents,
  type ApiFailureEnvelope,
  type FileEventFacetsData,
  type FileEventGroupsData,
  type PaginatedDataFileEventResource,
  type PaginatedDataRunHeader,
  type RunDetailData,
  type RunFacetsData,
} from "../../api/generated";
import {
  InspectionUnexpectedDataError,
  throwInspectionResponseError,
} from "../inspection/query-errors";
import type { EventFilters, HistoryFilters } from "./history-url-state";

const SURFACE = "History";

export function historyInfiniteQuery(filters: HistoryFilters) {
  return infiniteQueryOptions({
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PaginatedDataRunHeader) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<PaginatedDataRunHeader> =>
      readHistory(filters, pageParam),
    queryKey: [
      "history",
      filters.query,
      filters.status ?? null,
      filters.planId,
      filters.libraryId,
    ] as const,
  });
}

export function historyFacetsQuery(libraryId: string) {
  return queryOptions({
    queryFn: () => readHistoryFacets(libraryId),
    queryKey: ["history", "facets", libraryId] as const,
  });
}

export function runDetailQuery(runId: string) {
  return queryOptions({
    enabled: runId.length > 0,
    queryFn: () => readRun(runId),
    queryKey: ["history", runId, "detail"] as const,
  });
}

export function runEventsInfiniteQuery(runId: string, filters: EventFilters) {
  return infiniteQueryOptions({
    enabled: runId.length > 0,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PaginatedDataFileEventResource) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<PaginatedDataFileEventResource> =>
      readRunEvents(runId, filters, pageParam),
    queryKey: ["history", runId, "events", filters.status ?? null] as const,
  });
}

export function runEventFacetsQuery(runId: string) {
  return queryOptions({
    enabled: runId.length > 0,
    queryFn: () => readRunEventFacets(runId),
    queryKey: ["history", runId, "events", "facets"] as const,
  });
}

export function runEventGroupsInfiniteQuery(runId: string) {
  return infiniteQueryOptions({
    enabled: runId.length > 0,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: FileEventGroupsData) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<FileEventGroupsData> =>
      readRunEventGroups(runId, pageParam),
    queryKey: [
      "history",
      runId,
      "events",
      "groups",
      "target_directory",
    ] as const,
  });
}

async function readHistory(
  filters: HistoryFilters,
  cursor?: string,
): Promise<PaginatedDataRunHeader> {
  const response = await getHistory({
    baseUrl: location.origin,
    query: {
      cursor,
      library_id: filters.libraryId || undefined,
      plan_id: filters.planId || undefined,
      query: filters.query || undefined,
      status: filters.status,
    },
  });
  return dataOrThrow(response, "Run list");
}

async function readHistoryFacets(libraryId: string): Promise<RunFacetsData> {
  const response = await getHistoryFacets({
    baseUrl: location.origin,
    query: { library_id: libraryId || undefined },
  });
  return dataOrThrow(response, "Run facets");
}

async function readRun(runId: string): Promise<RunDetailData> {
  const response = await getRun({
    baseUrl: location.origin,
    path: { run_id: runId },
  });
  return dataOrThrow(response, "Run detail");
}

async function readRunEvents(
  runId: string,
  filters: EventFilters,
  cursor?: string,
): Promise<PaginatedDataFileEventResource> {
  const response = await getRunEvents({
    baseUrl: location.origin,
    path: { run_id: runId },
    query: { cursor, status: filters.status },
  });
  return dataOrThrow(response, "FileEvents");
}

async function readRunEventFacets(runId: string): Promise<FileEventFacetsData> {
  const response = await getRunEventFacets({
    baseUrl: location.origin,
    path: { run_id: runId },
  });
  return dataOrThrow(response, "FileEvent facets");
}

async function readRunEventGroups(
  runId: string,
  cursor?: string,
): Promise<FileEventGroupsData> {
  const response = await getRunEventGroups({
    baseUrl: location.origin,
    path: { run_id: runId },
    query: { cursor, group_by: "target_directory" },
  });
  return dataOrThrow(response, "FileEvent groups");
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
