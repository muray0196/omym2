/**
 * Summary: Owns URL-backed Run and FileEvent inspection filters.
 * Why: Keeps shared links and TanStack Query keys synchronized.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { FileEventStatus, RunStatus } from "../../api/generated";

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
      setOptional(updated, "query", next.query);
      setOptional(updated, "status", next.status);
      setOptional(updated, "plan_id", next.planId);
      setOptional(updated, "library_id", next.libraryId);
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
      setOptional(updated, "event_status", status);
      setParameters(updated, { replace: true });
    },
    [filters.status, parameters, setParameters],
  );
  return { filters, updateFilters };
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
