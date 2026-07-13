/**
 * Summary: Owns URL-backed Track search, status, hierarchy, drill-down, and group selection.
 * Why: Keeps shareable Library state synchronized with query keys while treating group keys as opaque.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { TrackGrouping, TrackStatus } from "../../api/generated";
import { trackGroupingLabel, trackStatusLabel } from "./library-catalog";

const TRACK_STATUSES = [
  "active",
  "removed",
] as const satisfies readonly TrackStatus[];
const ROOT_GROUPINGS = [
  "artist",
  "artist_album",
] as const satisfies readonly TrackGrouping[];
const TRACK_GROUPINGS = [
  "artist",
  "album",
  "disc",
  "artist_album",
] as const satisfies readonly TrackGrouping[];
const DEFAULT_GROUPING: TrackGrouping = "artist";
const PARAMETER_NAMES = [
  "query",
  "status",
  "group_by",
  "artist_key",
  "album_key",
  "group_key",
] as const;

export type LibraryBrowseFilters = {
  albumKey: string | undefined;
  artistKey: string | undefined;
  groupBy: TrackGrouping;
  groupKey: string | undefined;
  query: string;
  status: TrackStatus | undefined;
};

export const trackStatusOptions = TRACK_STATUSES.map((value) => ({
  label: trackStatusLabel(value),
  value,
}));

export const rootGroupingOptions = ROOT_GROUPINGS.map((value) => ({
  label: trackGroupingLabel(value),
  value,
}));

export function useLibraryBrowseFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(
    () => readLibraryBrowseFilters(searchParams),
    [searchParams],
  );

  const writeFilters = useCallback(
    (next: LibraryBrowseFilters) => {
      const parameters = new URLSearchParams(searchParams);
      setOptionalParameter(parameters, "query", next.query);
      setOptionalParameter(parameters, "status", next.status);
      setOptionalParameter(
        parameters,
        "group_by",
        next.groupBy === DEFAULT_GROUPING ? undefined : next.groupBy,
      );
      setOptionalParameter(parameters, "artist_key", next.artistKey);
      setOptionalParameter(parameters, "album_key", next.albumKey);
      setOptionalParameter(parameters, "group_key", next.groupKey);
      setSearchParams(parameters, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const updateFilters = useCallback(
    (changes: Partial<LibraryBrowseFilters>) => {
      writeFilters({ ...filters, ...changes });
    },
    [filters, writeFilters],
  );

  const changeRootGrouping = useCallback(
    (groupBy: TrackGrouping) => {
      writeFilters({
        ...filters,
        albumKey: undefined,
        artistKey: undefined,
        groupBy,
        groupKey: undefined,
      });
    },
    [filters, writeFilters],
  );

  const browseGroup = useCallback(
    (groupKey: string) => {
      if (filters.groupBy === "artist") {
        writeFilters({
          ...filters,
          artistKey: groupKey,
          groupBy: "album",
          groupKey: undefined,
        });
      } else if (filters.groupBy === "album") {
        writeFilters({
          ...filters,
          albumKey: groupKey,
          groupBy: "disc",
          groupKey: undefined,
        });
      }
    },
    [filters, writeFilters],
  );

  const backOneLevel = useCallback(() => {
    if (filters.groupBy === "disc") {
      writeFilters({
        ...filters,
        albumKey: undefined,
        groupBy: "album",
        groupKey: undefined,
      });
    } else if (filters.groupBy === "album") {
      writeFilters({
        ...filters,
        artistKey: undefined,
        groupBy: "artist",
        groupKey: undefined,
      });
    }
  }, [filters, writeFilters]);

  const clearGroup = useCallback(() => {
    updateFilters({ groupKey: undefined });
  }, [updateFilters]);

  const resetFilters = useCallback(() => {
    const parameters = new URLSearchParams(searchParams);
    for (const name of PARAMETER_NAMES) {
      parameters.delete(name);
    }
    setSearchParams(parameters, { replace: true });
  }, [searchParams, setSearchParams]);

  return {
    backOneLevel,
    browseGroup,
    changeRootGrouping,
    clearGroup,
    filters,
    hasActiveFilters:
      filters.query.length > 0 ||
      filters.status !== undefined ||
      filters.groupBy !== DEFAULT_GROUPING ||
      filters.artistKey !== undefined ||
      filters.albumKey !== undefined ||
      filters.groupKey !== undefined,
    resetFilters,
    selectGroup: (groupKey: string) => updateFilters({ groupKey }),
    updateFilters,
  };
}

function readLibraryBrowseFilters(
  searchParams: URLSearchParams,
): LibraryBrowseFilters {
  let groupBy =
    selectedValue(searchParams.get("group_by"), TRACK_GROUPINGS) ??
    DEFAULT_GROUPING;
  let artistKey = optionalValue(searchParams.get("artist_key"));
  let albumKey = optionalValue(searchParams.get("album_key"));

  if (groupBy === "album" && artistKey === undefined) {
    groupBy = DEFAULT_GROUPING;
  }
  if (groupBy === "disc" && albumKey === undefined) {
    groupBy = artistKey === undefined ? DEFAULT_GROUPING : "album";
  }
  if (groupBy === "artist" || groupBy === "artist_album") {
    artistKey = undefined;
    albumKey = undefined;
  } else if (groupBy === "album") {
    albumKey = undefined;
  }

  return {
    albumKey,
    artistKey,
    groupBy,
    groupKey: optionalValue(searchParams.get("group_key")),
    query: searchParams.get("query") ?? "",
    status: selectedValue(searchParams.get("status"), TRACK_STATUSES),
  };
}

function selectedValue<Value extends string>(
  rawValue: string | null,
  options: readonly Value[],
): Value | undefined {
  return options.find((option) => option === rawValue);
}

function optionalValue(rawValue: string | null) {
  return rawValue === null || rawValue.length === 0 ? undefined : rawValue;
}

function setOptionalParameter(
  searchParams: URLSearchParams,
  name: string,
  value: string | undefined,
) {
  if (value === undefined || value.length === 0) {
    searchParams.delete(name);
    return;
  }
  searchParams.set(name, value);
}
