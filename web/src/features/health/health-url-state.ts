/**
 * Summary: Owns URL-backed persisted Check filters and group drill-down.
 * Why: Keeps reloadable Health state synchronized with query keys and cursors.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { CheckIssueGrouping, CheckIssueType } from "../../api/generated";

const ISSUE_TYPES = [
  "db_file_missing",
  "unmanaged_file_exists",
  "content_hash_changed",
  "metadata_hash_changed",
  "current_path_differs_from_canonical_path",
  "companion_file_missing",
  "companion_content_hash_changed",
  "companion_current_path_differs_from_canonical_path",
  "companion_owner_missing",
  "unmanaged_companion_exists",
  "failed_companion_source_exists",
  "unprocessed_file_missing",
  "unprocessed_content_hash_changed",
  "duplicate_candidate",
  "plan_source_changed",
  "pending_file_event_exists",
  "library_unregistered",
  "library_stale",
  "library_blocked",
] as const satisfies readonly CheckIssueType[];
const GROUPINGS = [
  "issue_type",
  "severity",
  "path_root",
  "artist_album",
  "suggested_command",
  "library_id",
] as const satisfies readonly CheckIssueGrouping[];
const DEFAULT_GROUPING: CheckIssueGrouping = "issue_type";

export type HealthFilters = {
  groupBy: CheckIssueGrouping;
  groupKey: string | undefined;
  issueType: CheckIssueType | undefined;
  libraryId: string;
  query: string;
};

export const issueTypeOptions = ISSUE_TYPES;
export const groupingOptions = GROUPINGS;

export function useHealthFilters() {
  const [parameters, setParameters] = useSearchParams();
  const filters = useMemo<HealthFilters>(
    () => ({
      groupBy:
        selectedValue(parameters.get("group_by"), GROUPINGS) ??
        DEFAULT_GROUPING,
      groupKey: parameters.get("group_key") || undefined,
      issueType: selectedValue(parameters.get("issue_type"), ISSUE_TYPES),
      libraryId: parameters.get("library_id") ?? "",
      query: parameters.get("query") ?? "",
    }),
    [parameters],
  );

  const updateFilters = useCallback(
    (changes: Partial<HealthFilters>) => {
      const next = { ...filters, ...changes };
      const updated = new URLSearchParams(parameters);
      setOptional(updated, "query", next.query);
      setOptional(updated, "issue_type", next.issueType);
      setOptional(updated, "library_id", next.libraryId);
      setOptional(
        updated,
        "group_by",
        next.groupBy === DEFAULT_GROUPING ? undefined : next.groupBy,
      );
      setOptional(updated, "group_key", next.groupKey);
      setParameters(updated, { replace: true });
    },
    [filters, parameters, setParameters],
  );

  const resetFilters = useCallback(() => {
    const updated = new URLSearchParams(parameters);
    for (const name of [
      "query",
      "issue_type",
      "library_id",
      "group_by",
      "group_key",
    ])
      updated.delete(name);
    setParameters(updated, { replace: true });
  }, [parameters, setParameters]);

  return {
    clearGroup: () => updateFilters({ groupKey: undefined }),
    filters,
    hasActiveFilters: Boolean(
      filters.query ||
      filters.issueType ||
      filters.libraryId ||
      filters.groupBy !== DEFAULT_GROUPING ||
      filters.groupKey,
    ),
    resetFilters,
    updateFilters,
  };
}

function selectedValue<Value extends string>(
  raw: string | null,
  values: readonly Value[],
): Value | undefined {
  return values.find((value) => value === raw);
}

function setOptional(
  parameters: URLSearchParams,
  name: string,
  value: string | undefined,
) {
  if (value === undefined || value.length === 0) parameters.delete(name);
  else parameters.set(name, value);
}
