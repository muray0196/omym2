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
  type FileEventFacetsData,
  type FileEventGroupsData,
  type PaginatedDataFileEventResource,
  type PaginatedDataRunHeader,
  type RunDetailData,
  type RunFacetsData,
} from "../../api/generated";
import { inspectionDataOrThrow } from "../inspection/query-errors";
import type { EventFilters, HistoryFilters } from "./history-url-state";

const SURFACE = "History";

export function historyInfiniteQuery(filters: HistoryFilters) {
  return infiniteQueryOptions({
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PaginatedDataRunHeader) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam, signal }): Promise<PaginatedDataRunHeader> =>
      readHistory(filters, pageParam, signal),
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
    queryFn: ({ signal }) => readHistoryFacets(libraryId, signal),
    queryKey: ["history", "facets", libraryId] as const,
  });
}

export function runDetailQuery(runId: string) {
  return queryOptions({
    enabled: runId.length > 0,
    queryFn: ({ signal }) => readRun(runId, signal),
    queryKey: ["history", runId, "detail"] as const,
  });
}

export function runEventsInfiniteQuery(runId: string, filters: EventFilters) {
  return infiniteQueryOptions({
    enabled: runId.length > 0,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PaginatedDataFileEventResource) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam, signal }): Promise<PaginatedDataFileEventResource> =>
      readRunEvents(runId, filters, pageParam, signal),
    queryKey: ["history", runId, "events", filters.status ?? null] as const,
  });
}

export function runEventFacetsQuery(runId: string) {
  return queryOptions({
    enabled: runId.length > 0,
    queryFn: ({ signal }) => readRunEventFacets(runId, signal),
    queryKey: ["history", runId, "events", "facets"] as const,
  });
}

export function runEventGroupsInfiniteQuery(runId: string) {
  return infiniteQueryOptions({
    enabled: runId.length > 0,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: FileEventGroupsData) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam, signal }): Promise<FileEventGroupsData> =>
      readRunEventGroups(runId, pageParam, signal),
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
  cursor: string | undefined,
  signal: AbortSignal,
): Promise<PaginatedDataRunHeader> {
  const response = await getHistory({
    baseUrl: location.origin,
    signal,
    query: {
      cursor,
      library_id: filters.libraryId || undefined,
      plan_id: filters.planId || undefined,
      query: filters.query || undefined,
      status: filters.status,
    },
  });
  return inspectionDataOrThrow(response, `${SURFACE} Run list`);
}

async function readHistoryFacets(
  libraryId: string,
  signal: AbortSignal,
): Promise<RunFacetsData> {
  const response = await getHistoryFacets({
    baseUrl: location.origin,
    query: { library_id: libraryId || undefined },
    signal,
  });
  return inspectionDataOrThrow(response, `${SURFACE} Run facets`);
}

async function readRun(
  runId: string,
  signal: AbortSignal,
): Promise<RunDetailData> {
  const response = await getRun({
    baseUrl: location.origin,
    path: { run_id: runId },
    signal,
  });
  return inspectionDataOrThrow(response, `${SURFACE} Run detail`);
}

async function readRunEvents(
  runId: string,
  filters: EventFilters,
  cursor: string | undefined,
  signal: AbortSignal,
): Promise<PaginatedDataFileEventResource> {
  const response = await getRunEvents({
    baseUrl: location.origin,
    path: { run_id: runId },
    query: { cursor, status: filters.status },
    signal,
  });
  return inspectionDataOrThrow(response, `${SURFACE} FileEvents`);
}

async function readRunEventFacets(
  runId: string,
  signal: AbortSignal,
): Promise<FileEventFacetsData> {
  const response = await getRunEventFacets({
    baseUrl: location.origin,
    path: { run_id: runId },
    signal,
  });
  return inspectionDataOrThrow(response, `${SURFACE} FileEvent facets`);
}

async function readRunEventGroups(
  runId: string,
  cursor: string | undefined,
  signal: AbortSignal,
): Promise<FileEventGroupsData> {
  const response = await getRunEventGroups({
    baseUrl: location.origin,
    path: { run_id: runId },
    query: { cursor, group_by: "target_directory" },
    signal,
  });
  return inspectionDataOrThrow(response, `${SURFACE} FileEvent groups`);
}
