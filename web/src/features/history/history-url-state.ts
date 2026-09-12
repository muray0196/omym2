/**
 * Summary: Owns URL-backed Run and FileEvent inspection filters.
 * Why: Keeps shared links and TanStack Query keys synchronized.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { FileEventStatus, RunStatus } from "../../api/generated";
import { selectedValue, setOptionalParameter } from "../../ui/search-params";

const RUN_STATUSES = [
  "running",
  "succeeded",
  "partial_failed",
  "failed",
] as const satisfies readonly RunStatus[];
const EVENT_STATUSES = [
  "pending",
  "succeeded",
  "failed",
] as const satisfies readonly FileEventStatus[];

export type HistoryFilters = {
  libraryId: string;
  planId: string;
  query: string;
  status: RunStatus | undefined;
};

export type EventFilters = { status: FileEventStatus | undefined };

export const runStatusOptions = RUN_STATUSES;
export const eventStatusOptions = EVENT_STATUSES;

export function useHistoryFilters() {
  const [parameters, setParameters] = useSearchParams();
  const filters = useMemo<HistoryFilters>(
    () => ({
      libraryId: parameters.get("library_id") ?? "",
      planId: parameters.get("plan_id") ?? "",
      query: parameters.get("query") ?? "",
      status: selectedValue(parameters.get("status"), RUN_STATUSES),
    }),
    [parameters],
  );

  const updateFilters = useCallback(
    (changes: Partial<HistoryFilters>) => {
      const next = { ...filters, ...changes };
      const updated = new URLSearchParams(parameters);
      setOptionalParameter(updated, "query", next.query);
      setOptionalParameter(updated, "status", next.status);
      setOptionalParameter(updated, "plan_id", next.planId);
      setOptionalParameter(updated, "library_id", next.libraryId);
      setParameters(updated, { replace: true });
    },
    [filters, parameters, setParameters],
  );

  const resetFilters = useCallback(() => {
    const updated = new URLSearchParams(parameters);
    for (const name of ["query", "status", "plan_id", "library_id"])
      updated.delete(name);
    setParameters(updated, { replace: true });
  }, [parameters, setParameters]);

  return {
    filters,
    hasActiveFilters: Boolean(
      filters.query || filters.status || filters.planId || filters.libraryId,
    ),
    resetFilters,
    updateFilters,
  };
}

export function useEventFilters() {
  const [parameters, setParameters] = useSearchParams();
  const filters = useMemo<EventFilters>(
    () => ({
      status: selectedValue(parameters.get("event_status"), EVENT_STATUSES),
    }),
    [parameters],
  );
  const updateFilters = useCallback(
    (changes: Partial<EventFilters>) => {
      const updated = new URLSearchParams(parameters);
      const status = "status" in changes ? changes.status : filters.status;
      setOptionalParameter(updated, "event_status", status);
      setParameters(updated, { replace: true });
    },
    [filters.status, parameters, setParameters],
  );
  return { filters, updateFilters };
}
