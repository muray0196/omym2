/**
 * Summary: Defines generated-SDK queries for Track pages, facets, groups, and detail.
 * Why: Keeps read-only Library transport typed, deduplicated, and cursor keys opaque.
 */
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getTrack as requestTrack,
  getTrackFacets,
  getTrackGroups,
  listTracks,
  type ApiErrorCode,
  type ApiFailureEnvelope,
  type PaginatedDataTrackResource,
  type TrackFacetsData,
  type TrackGroupsData,
  type TrackResource,
} from "../../api/generated";
import type { LibraryBrowseFilters } from "./library-url-state";

export type LibraryTrack = TrackResource;
export type LibraryTrackFacets = TrackFacetsData;
export type LibraryTrackGroups = TrackGroupsData;

export class LibraryApiError extends Error {
  readonly envelope: ApiFailureEnvelope;

  constructor(envelope: ApiFailureEnvelope) {
    super("Library inspection returned a typed API failure.");
    this.name = "LibraryApiError";
    this.envelope = envelope;
  }
}

export class LibraryTransportError extends Error {
  constructor() {
    super("The local OMYM2 service could not be reached.");
    this.name = "LibraryTransportError";
  }
}

export class LibraryUnexpectedDataError extends Error {
  constructor() {
    super("Library inspection returned no readable data.");
    this.name = "LibraryUnexpectedDataError";
  }
}

export function tracksInfiniteQuery(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
) {
  return infiniteQueryOptions({
    enabled: libraryId !== undefined,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PaginatedDataTrackResource) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }) => readTracksPage(libraryId, filters, pageParam),
    queryKey: [
      "tracks",
      libraryId ?? null,
      filters.query,
      filters.status ?? null,
      filters.groupBy,
      filters.groupKey ?? null,
    ] as const,
  });
}

export function trackFacetsQuery(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
) {
  return queryOptions({
    enabled: libraryId !== undefined,
    queryFn: () => readTrackFacets(libraryId, filters),
    queryKey: ["tracks", libraryId ?? null, "facets", filters.query] as const,
  });
}

export function trackGroupsInfiniteQuery(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
) {
  return infiniteQueryOptions({
    enabled: libraryId !== undefined,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: TrackGroupsData) =>
      lastPage.page.next_cursor ?? undefined,
    queryFn: ({ pageParam }) => readTrackGroups(libraryId, filters, pageParam),
    queryKey: [
      "tracks",
      libraryId ?? null,
      "groups",
      filters.groupBy,
      parentKey(filters) ?? null,
      filters.query,
      filters.status ?? null,
    ] as const,
  });
}

export function trackDetailQuery(trackId: string) {
  return queryOptions({
    enabled: trackId.length > 0,
    queryFn: () => readTrack(trackId),
    queryKey: ["tracks", "detail", trackId] as const,
  });
}

export function libraryErrorHasCode(error: Error, code: ApiErrorCode) {
  return (
    error instanceof LibraryApiError &&
    error.envelope.errors.some((diagnostic) => diagnostic.code === code)
  );
}

async function readTracksPage(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
  cursor: string | undefined,
): Promise<PaginatedDataTrackResource> {
  const response = await listTracks({
    baseUrl: globalThis.location.origin,
    query: {
      cursor,
      group_by: filters.groupKey === undefined ? undefined : filters.groupBy,
      group_key: filters.groupKey,
      library_id: libraryId,
      query: filters.query.length === 0 ? undefined : filters.query,
      status: filters.status,
    },
  });

  if (response.error !== undefined) {
    throwLibraryResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new LibraryUnexpectedDataError();
  }
  return response.data.data;
}

async function readTrackFacets(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
): Promise<TrackFacetsData> {
  const response = await getTrackFacets({
    baseUrl: globalThis.location.origin,
    query: {
      library_id: libraryId,
      query: filters.query.length === 0 ? undefined : filters.query,
    },
  });

  if (response.error !== undefined) {
    throwLibraryResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new LibraryUnexpectedDataError();
  }
  return response.data.data;
}

async function readTrackGroups(
  libraryId: string | undefined,
  filters: LibraryBrowseFilters,
  cursor: string | undefined,
): Promise<TrackGroupsData> {
  const response = await getTrackGroups({
    baseUrl: globalThis.location.origin,
    query: {
      cursor,
      group_by: filters.groupBy,
      library_id: libraryId,
      parent_key: parentKey(filters),
      query: filters.query.length === 0 ? undefined : filters.query,
      status: filters.status,
    },
  });

  if (response.error !== undefined) {
    throwLibraryResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new LibraryUnexpectedDataError();
  }
  return response.data.data;
}

async function readTrack(trackId: string): Promise<TrackResource> {
  const response = await requestTrack({
    baseUrl: globalThis.location.origin,
    path: { track_id: trackId },
  });

  if (response.error !== undefined) {
    throwLibraryResponseError(response.error, response.response);
  }
  if (response.data.data === null) {
    throw new LibraryUnexpectedDataError();
  }
  return response.data.data;
}

function parentKey(filters: LibraryBrowseFilters) {
  if (filters.groupBy === "album") {
    return filters.artistKey;
  }
  if (filters.groupBy === "disc") {
    return filters.albumKey;
  }
  return undefined;
}

function throwLibraryResponseError(
  envelope: ApiFailureEnvelope,
  response: Response | undefined,
): never {
  if (response === undefined) {
    throw new LibraryTransportError();
  }
  throw new LibraryApiError(envelope);
}
