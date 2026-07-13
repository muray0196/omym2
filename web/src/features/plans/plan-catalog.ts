/**
 * Summary: Maps Plan catalog values to visible labels and neutral presentation tones.
 * Why: Preserves forward-compatible unknown values without inferring permitted operations.
 */
import { planCopy } from "./plan-copy";
import type {
  ActionStatus,
  ActionType,
  PlanActionReason,
  PlanStatus,
  PlanType,
} from "../../api/generated";
import type { IconName } from "../../ui/icon";

export type PlanTone = "info" | "success" | "warning" | "danger" | "neutral";
export type PlanCatalogPresentation = {
  icon: IconName;
  label: string;
  meaning: string;
  tone: PlanTone;
};

const PLAN_STATUS_PRESENTATIONS = {
  ready: {
    icon: "info",
    label: "Ready",
    meaning: "The Plan is reviewed and awaits a backend-authorized next step.",
    tone: "info",
  },
  applying: {
    icon: "info",
    label: "Applying",
    meaning: "An Apply Operation is processing the Plan's recorded actions.",
    tone: "info",
  },
  applied: {
    icon: "check",
    label: "Applied",
    meaning: "The Plan reached a terminal state with its Apply run recorded.",
    tone: "success",
  },
  partial_failed: {
    icon: "warning",
    label: "Partially failed",
    meaning: "Confirmed work and failures coexist; no rollback is implied.",
    tone: "warning",
  },
  failed: {
    icon: "warning",
    label: "Failed",
    meaning: "The Plan reached a terminal failed state.",
    tone: "danger",
  },
  cancelled: {
    icon: "close",
    label: "Cancelled",
    meaning: "The ready Plan was cancelled and cannot be applied.",
    tone: "neutral",
  },
  expired: {
    icon: "warning",
    label: "Expired",
    meaning: "The Plan is terminal and no longer eligible for execution.",
    tone: "warning",
  },
} satisfies Record<PlanStatus, PlanCatalogPresentation>;

const PLAN_TYPE_PRESENTATIONS = {
  add: {
    icon: "info",
    label: "Add",
    meaning: "Reviews music to add to the selected Library before Apply.",
    tone: "info",
  },
  organize: {
    icon: "info",
    label: "Organize",
    meaning: "Reviews canonical path organization before Apply.",
    tone: "info",
  },
  refresh: {
    icon: "info",
    label: "Refresh",
    meaning: "Reviews metadata refresh work for managed Tracks before Apply.",
    tone: "info",
  },
  undo: {
    icon: "warning",
    label: "Undo",
    meaning: "Reviews a reversal derived from one completed Run before Apply.",
    tone: "warning",
  },
} satisfies Record<PlanType, PlanCatalogPresentation>;

const ACTION_STATUS_PRESENTATIONS = {
  planned: {
    icon: "info",
    label: "Planned",
    meaning: "The action is recorded and awaits Plan execution.",
    tone: "info",
  },
  blocked: {
    icon: "warning",
    label: "Blocked",
    meaning: "A planning problem prevents this action from being attempted.",
    tone: "warning",
  },
  applied: {
    icon: "check",
    label: "Applied",
    meaning: "The action completed or required no FileEvent mutation.",
    tone: "success",
  },
  failed: {
    icon: "warning",
    label: "Failed",
    meaning: "The action failed an Apply precondition or attempted work.",
    tone: "danger",
  },
} satisfies Record<ActionStatus, PlanCatalogPresentation>;

const ACTION_TYPE_PRESENTATIONS = {
  move: {
    icon: "info",
    label: "Move",
    meaning: "Moves one Library music file from its recorded source to target.",
    tone: "info",
  },
  skip: {
    icon: "close",
    label: "Skip",
    meaning: "Records reviewed work that requires no file mutation.",
    tone: "neutral",
  },
  refresh_metadata: {
    icon: "info",
    label: "Refresh metadata",
    meaning: "Refreshes Track metadata and hashes without moving a file.",
    tone: "info",
  },
} satisfies Record<ActionType, PlanCatalogPresentation>;

const REASON_PRESENTATIONS = {
  target_exists: {
    icon: "warning",
    label: "Target already exists",
    meaning: "The recorded target path is already occupied.",
    tone: "warning",
  },
  missing_required_metadata: {
    icon: "warning",
    label: "Missing required metadata",
    meaning: "Required metadata was unavailable when the action was planned.",
    tone: "warning",
  },
  invalid_path: {
    icon: "warning",
    label: "Invalid path",
    meaning: "The recorded path violates the Library path policy.",
    tone: "warning",
  },
  source_missing: {
    icon: "warning",
    label: "Source missing",
    meaning: "The recorded source file is no longer present.",
    tone: "warning",
  },
  source_changed: {
    icon: "warning",
    label: "Source changed",
    meaning: "The source no longer matches the state recorded by the Plan.",
    tone: "warning",
  },
  duplicate_hash: {
    icon: "warning",
    label: "Duplicate content hash",
    meaning: "Another managed Track has the same recorded content hash.",
    tone: "warning",
  },
  operation_interrupted: {
    icon: "warning",
    label: "Operation interrupted",
    meaning: "The attempted mutation outcome could not be confirmed.",
    tone: "danger",
  },
} satisfies Record<PlanActionReason, PlanCatalogPresentation>;

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
  return planStatusPresentation(value).label;
}

export function planStatusTone(value: string) {
  return planStatusPresentation(value).tone;
}

export function planStatusIcon(value: string): IconName {
  return planStatusPresentation(value).icon;
}

export function planStatusPresentation(value: string): PlanCatalogPresentation {
  return presentationFor(
    value,
    PLAN_STATUS_PRESENTATIONS,
    planCopy.unknown.status,
  );
}

export function actionStatusLabel(value: string) {
  return actionStatusPresentation(value).label;
}

export function actionStatusTone(value: string) {
  return actionStatusPresentation(value).tone;
}

export function actionStatusIcon(value: string): IconName {
  return actionStatusPresentation(value).icon;
}

export function actionStatusPresentation(
  value: string,
): PlanCatalogPresentation {
  return presentationFor(
    value,
    ACTION_STATUS_PRESENTATIONS,
    planCopy.unknown.status,
  );
}

export function planTypeLabel(value: string) {
  return planTypePresentation(value).label;
}

export function planTypePresentation(value: string): PlanCatalogPresentation {
  return presentationFor(value, PLAN_TYPE_PRESENTATIONS, planCopy.unknown.type);
}

export function actionTypeLabel(value: string) {
  return actionTypePresentation(value).label;
}

export function actionTypePresentation(value: string): PlanCatalogPresentation {
  return presentationFor(
    value,
    ACTION_TYPE_PRESENTATIONS,
    planCopy.unknown.actionType,
  );
}

export function reasonLabel(value: string | null) {
  if (value === null) {
    return "—";
  }
  return reasonPresentation(value).label;
}

export function reasonPresentation(value: string): PlanCatalogPresentation {
  return presentationFor(value, REASON_PRESENTATIONS, planCopy.unknown.reason);
}

export function actionGroupingLabel(value: string) {
  return labelFor(value, ACTION_GROUPING_LABELS, planCopy.unknown.grouping);
}

export function actionGroupValueLabel(
  groupBy: string,
  key: string,
  serverLabel: string,
) {
  if (groupBy === "status") return actionStatusLabel(key);
  if (groupBy === "action_type") return actionTypeLabel(key);
  if (groupBy === "block_reason") return reasonLabel(key);
  return serverLabel;
}

function labelFor(
  value: string,
  labels: Record<string, string>,
  unknownPrefix: string,
) {
  return labels[value] ?? `${unknownPrefix}: ${value}`;
}

function presentationFor(
  value: string,
  presentations: Partial<Record<string, PlanCatalogPresentation>>,
  unknownPrefix: string,
): PlanCatalogPresentation {
  return (
    presentations[value] ?? {
      icon: "info",
      label: `${unknownPrefix}: ${value}`,
      meaning: `No bundled presentation is available for the raw stable code ${value}.`,
      tone: "neutral",
    }
  );
}
