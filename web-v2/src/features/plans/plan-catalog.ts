/**
 * Summary: Maps Plan catalog values to visible labels and neutral presentation tones.
 * Why: Preserves forward-compatible unknown values without inferring permitted operations.
 */
import { planCopy } from "./plan-copy";

export type PlanTone = "info" | "success" | "warning" | "danger" | "neutral";

const PLAN_STATUS_LABELS = {
  ready: "Ready",
  applying: "Applying",
  applied: "Applied",
  partial_failed: "Partially failed",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
} as const;

const PLAN_STATUS_TONES: Record<keyof typeof PLAN_STATUS_LABELS, PlanTone> = {
  ready: "info",
  applying: "info",
  applied: "success",
  partial_failed: "warning",
  failed: "danger",
  cancelled: "neutral",
  expired: "warning",
};

const PLAN_TYPE_LABELS = {
  add: "Add",
  organize: "Organize",
  refresh: "Refresh",
  undo: "Undo",
} as const;

const ACTION_STATUS_LABELS = {
  planned: "Planned",
  blocked: "Blocked",
  applied: "Applied",
  failed: "Failed",
} as const;

const ACTION_STATUS_TONES: Record<keyof typeof ACTION_STATUS_LABELS, PlanTone> =
  {
    planned: "info",
    blocked: "warning",
    applied: "success",
    failed: "danger",
  };

const ACTION_TYPE_LABELS = {
  move: "Move",
  skip: "Skip",
  refresh_metadata: "Refresh metadata",
} as const;

const REASON_LABELS = {
  target_exists: "Target already exists",
  missing_required_metadata: "Missing required metadata",
  invalid_path: "Invalid path",
  source_missing: "Source missing",
  source_changed: "Source changed",
  duplicate_hash: "Duplicate content hash",
  operation_interrupted: "Operation interrupted",
} as const;

const ACTION_GROUPING_LABELS = {
  target_directory: "Target directory",
  source_directory: "Source directory",
  artist_album: "Artist and album",
  action_type: "Action type",
  status: "Status",
  block_reason: "Block reason",
  extension: "File extension",
} as const;

export function planStatusLabel(value: string) {
  return labelFor(value, PLAN_STATUS_LABELS, planCopy.unknown.status);
}

export function planStatusTone(value: string) {
  return toneFor(value, PLAN_STATUS_TONES);
}

export function actionStatusLabel(value: string) {
  return labelFor(value, ACTION_STATUS_LABELS, planCopy.unknown.status);
}

export function actionStatusTone(value: string) {
  return toneFor(value, ACTION_STATUS_TONES);
}

export function planTypeLabel(value: string) {
  return labelFor(value, PLAN_TYPE_LABELS, planCopy.unknown.type);
}

export function actionTypeLabel(value: string) {
  return labelFor(value, ACTION_TYPE_LABELS, planCopy.unknown.actionType);
}

export function reasonLabel(value: string | null) {
  if (value === null) {
    return "—";
  }
  return labelFor(value, REASON_LABELS, planCopy.unknown.reason);
}

export function actionGroupingLabel(value: string) {
  return labelFor(value, ACTION_GROUPING_LABELS, planCopy.unknown.grouping);
}

function labelFor(
  value: string,
  labels: Record<string, string>,
  unknownPrefix: string,
) {
  return labels[value] ?? `${unknownPrefix}: ${value}`;
}

function toneFor(value: string, tones: Partial<Record<string, PlanTone>>) {
  return tones[value] ?? "neutral";
}
