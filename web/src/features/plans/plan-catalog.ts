/**
 * Summary: Maps closed Plan catalogs to visible labels and presentation tones.
 * Why: Gives every coordinated generated enum value an exhaustive presentation.
 */
import type {
  ActionStatus,
  ActionType,
  PlanActionGrouping,
  PlanActionReason,
  PlanStatus,
  PlanType,
} from "../../api/generated";
import { catalogValueOrThrow } from "../../ui/catalog";
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
  move_lyrics: {
    icon: "info",
    label: "Move lyrics",
    meaning: "Moves one managed lyrics file with its associated Track.",
    tone: "info",
  },
  move_artwork: {
    icon: "info",
    label: "Move artwork",
    meaning: "Moves one managed artwork file under its deterministic owner.",
    tone: "info",
  },
  move_unprocessed: {
    icon: "info",
    label: "Move unprocessed file",
    meaning:
      "Moves one reviewed unclaimed file into the configured unprocessed area.",
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
  companion_owner_blocked: {
    icon: "warning",
    label: "Companion owner blocked",
    meaning:
      "The companion file cannot proceed because its owning audio action is blocked.",
    tone: "warning",
  },
  companion_association_ambiguous: {
    icon: "warning",
    label: "Companion association is ambiguous",
    meaning:
      "The companion file could not be associated with one owner deterministically.",
    tone: "warning",
  },
  companion_dependency_failed: {
    icon: "warning",
    label: "Companion dependency failed",
    meaning:
      "A required action did not complete, so this companion mutation was not attempted.",
    tone: "danger",
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
} as const satisfies Record<PlanActionGrouping, string>;

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
  return catalogValueOrThrow("Plan status", value, PLAN_STATUS_PRESENTATIONS);
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
  return catalogValueOrThrow(
    "PlanAction status",
    value,
    ACTION_STATUS_PRESENTATIONS,
  );
}

export function planTypeLabel(value: string) {
  return planTypePresentation(value).label;
}

export function planTypePresentation(value: string): PlanCatalogPresentation {
  return catalogValueOrThrow("Plan type", value, PLAN_TYPE_PRESENTATIONS);
}

export function actionTypeLabel(value: string) {
  return actionTypePresentation(value).label;
}

export function actionTypePresentation(value: string): PlanCatalogPresentation {
  return catalogValueOrThrow(
    "PlanAction type",
    value,
    ACTION_TYPE_PRESENTATIONS,
  );
}

export function reasonLabel(value: string | null) {
  if (value === null) {
    return "—";
  }
  return reasonPresentation(value).label;
}

export function reasonPresentation(value: string): PlanCatalogPresentation {
  return catalogValueOrThrow("PlanAction reason", value, REASON_PRESENTATIONS);
}

export function actionGroupingLabel(value: string) {
  return catalogValueOrThrow(
    "PlanAction grouping",
    value,
    ACTION_GROUPING_LABELS,
  );
}

export function actionGroupValueLabel(
  groupBy: PlanActionGrouping,
  key: string,
  serverLabel: string,
) {
  if (groupBy === "status") {
    return catalogValueOrThrow(
      "PlanAction status",
      key,
      ACTION_STATUS_PRESENTATIONS,
    ).label;
  }
  if (groupBy === "action_type") {
    return catalogValueOrThrow(
      "PlanAction type",
      key,
      ACTION_TYPE_PRESENTATIONS,
    ).label;
  }
  if (groupBy === "block_reason") {
    return catalogValueOrThrow("PlanAction reason", key, REASON_PRESENTATIONS)
      .label;
  }
  return serverLabel;
}
