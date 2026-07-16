/**
 * Summary: Owns URL-backed Plan and PlanAction inspection filters.
 * Why: Keeps shareable browse state and TanStack Query keys synchronized without local duplicates.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type {
  ActionStatus,
  ActionType,
  PlanActionGrouping,
  PlanActionReason,
  PlanStatus,
  PlanType,
} from "../../api/generated";
import {
  actionGroupingLabel,
  actionStatusLabel,
  actionTypeLabel,
  planStatusLabel,
  planTypeLabel,
  reasonLabel,
} from "./plan-catalog";

const PLAN_STATUSES = [
  "ready",
  "applying",
  "applied",
  "partial_failed",
  "failed",
  "cancelled",
  "expired",
] as const satisfies readonly PlanStatus[];

const PLAN_TYPES = [
  "add",
  "organize",
  "refresh",
  "undo",
] as const satisfies readonly PlanType[];

const ACTION_STATUSES = [
  "planned",
  "blocked",
  "applied",
  "failed",
] as const satisfies readonly ActionStatus[];

const ACTION_TYPES = [
  "move",
  "move_lyrics",
  "move_artwork",
  "move_unprocessed",
  "skip",
  "refresh_metadata",
] as const satisfies readonly ActionType[];

const ACTION_REASONS = [
  "target_exists",
  "missing_required_metadata",
  "invalid_path",
  "source_missing",
  "source_changed",
  "duplicate_hash",
  "companion_owner_blocked",
  "companion_association_ambiguous",
  "companion_dependency_failed",
  "operation_interrupted",
] as const satisfies readonly PlanActionReason[];

const ACTION_GROUPINGS = [
  "target_directory",
  "source_directory",
  "artist_album",
  "action_type",
  "status",
  "block_reason",
  "extension",
] as const satisfies readonly PlanActionGrouping[];

const DEFAULT_ACTION_GROUPING: PlanActionGrouping = "status";

const LIST_PARAMETER_NAMES = ["query", "status", "type", "blocked"] as const;
const ACTION_FILTER_PARAMETER_NAMES = [
  "action_query",
  "action_status",
  "action_type",
  "reason",
  "group_by",
  "group_key",
] as const;
export type PlanListFilters = {
  blocked: boolean;
  query: string;
  status: PlanStatus | undefined;
  type: PlanType | undefined;
};

export type PlanActionFilters = {
  actionType: ActionType | undefined;
  groupBy: PlanActionGrouping;
  groupKey: string | undefined;
  query: string;
  reason: PlanActionReason | undefined;
  status: ActionStatus | undefined;
};

export const planStatusOptions = PLAN_STATUSES.map((value) => ({
  label: planStatusLabel(value),
  value,
}));

export const planTypeOptions = PLAN_TYPES.map((value) => ({
  label: planTypeLabel(value),
  value,
}));

export const actionStatusOptions = ACTION_STATUSES.map((value) => ({
  label: actionStatusLabel(value),
  value,
}));

export const actionTypeOptions = ACTION_TYPES.map((value) => ({
  label: actionTypeLabel(value),
  value,
}));

export const actionReasonOptions = ACTION_REASONS.map((value) => ({
  label: reasonLabel(value),
  value,
}));

export const actionGroupingOptions = ACTION_GROUPINGS.map((value) => ({
  label: actionGroupingLabel(value),
  value,
}));

export function usePlanListFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(
    () => readPlanListFilters(searchParams),
    [searchParams],
  );

  const updateFilters = useCallback(
    (changes: Partial<PlanListFilters>) => {
      const next = { ...filters, ...changes };
      const parameters = new URLSearchParams(searchParams);
      setOptionalParameter(parameters, "query", next.query);
      setOptionalParameter(parameters, "status", next.status);
      setOptionalParameter(parameters, "type", next.type);
      setOptionalParameter(
        parameters,
        "blocked",
        next.blocked ? "true" : undefined,
      );
      setSearchParams(parameters, { replace: true });
    },
    [filters, searchParams, setSearchParams],
  );

  const resetFilters = useCallback(() => {
    const parameters = new URLSearchParams(searchParams);
    deleteParameters(parameters, LIST_PARAMETER_NAMES);
    setSearchParams(parameters, { replace: true });
  }, [searchParams, setSearchParams]);

  return {
    filters,
    hasActiveFilters:
      filters.query.length > 0 ||
      filters.status !== undefined ||
      filters.type !== undefined ||
      filters.blocked,
    resetFilters,
    updateFilters,
  };
}

export function usePlanActionFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(
    () => readPlanActionFilters(searchParams),
    [searchParams],
  );

  const updateFilters = useCallback(
    (changes: Partial<PlanActionFilters>) => {
      const next = { ...filters, ...changes };
      const parameters = new URLSearchParams(searchParams);
      setOptionalParameter(parameters, "action_query", next.query);
      setOptionalParameter(parameters, "action_status", next.status);
      setOptionalParameter(parameters, "action_type", next.actionType);
      setOptionalParameter(parameters, "reason", next.reason);
      setOptionalParameter(
        parameters,
        "group_by",
        next.groupBy === DEFAULT_ACTION_GROUPING ? undefined : next.groupBy,
      );
      setOptionalParameter(parameters, "group_key", next.groupKey);
      setSearchParams(parameters, { replace: true });
    },
    [filters, searchParams, setSearchParams],
  );

  const resetFilters = useCallback(() => {
    const parameters = new URLSearchParams(searchParams);
    deleteParameters(parameters, ACTION_FILTER_PARAMETER_NAMES);
    setSearchParams(parameters, { replace: true });
  }, [searchParams, setSearchParams]);

  const clearGroup = useCallback(() => {
    const parameters = new URLSearchParams(searchParams);
    parameters.delete("group_key");
    setSearchParams(parameters, { replace: true });
  }, [searchParams, setSearchParams]);

  return {
    clearGroup,
    filters,
    hasActiveFilters:
      filters.query.length > 0 ||
      filters.status !== undefined ||
      filters.actionType !== undefined ||
      filters.reason !== undefined ||
      filters.groupBy !== DEFAULT_ACTION_GROUPING ||
      filters.groupKey !== undefined,
    resetFilters,
    updateFilters,
  };
}

function readPlanListFilters(searchParams: URLSearchParams): PlanListFilters {
  return {
    blocked: searchParams.get("blocked") === "true",
    query: searchParams.get("query") ?? "",
    status: selectedValue(searchParams.get("status"), PLAN_STATUSES),
    type: selectedValue(searchParams.get("type"), PLAN_TYPES),
  };
}

function readPlanActionFilters(
  searchParams: URLSearchParams,
): PlanActionFilters {
  const groupBy =
    selectedValue(searchParams.get("group_by"), ACTION_GROUPINGS) ??
    DEFAULT_ACTION_GROUPING;
  const selectedGroupKey = searchParams.get("group_key");

  return {
    actionType: selectedValue(searchParams.get("action_type"), ACTION_TYPES),
    groupBy,
    groupKey:
      selectedGroupKey === null || selectedGroupKey.length === 0
        ? undefined
        : selectedGroupKey,
    query: searchParams.get("action_query") ?? "",
    reason: selectedValue(searchParams.get("reason"), ACTION_REASONS),
    status: selectedValue(searchParams.get("action_status"), ACTION_STATUSES),
  };
}

function selectedValue<Value extends string>(
  rawValue: string | null,
  options: readonly Value[],
): Value | undefined {
  return options.find((option) => option === rawValue);
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

function deleteParameters(
  searchParams: URLSearchParams,
  names: readonly string[],
) {
  for (const name of names) {
    searchParams.delete(name);
  }
}
