/**
 * Summary: Maps durable Operation catalog values to labels, meanings, tones, and icons.
 * Why: Keeps known and newer server values visible without inferring lifecycle behavior.
 */
import type {
  OperationKind,
  OperationResultResource,
  OperationStatus,
} from "../../api/generated";
import type { IconName } from "../../ui/icon";
import { operationCopy } from "./operation-copy";

export type OperationTone =
  "info" | "success" | "warning" | "danger" | "neutral";

export type OperationCatalogPresentation = Readonly<{
  icon: IconName;
  label: string;
  meaning: string;
  tone: OperationTone;
}>;

export type OperationResultKind = OperationResultResource["kind"];

const OPERATION_KIND_PRESENTATIONS = {
  add_plan: {
    icon: "info",
    label: "Create Add Plan",
    meaning:
      "Scans a selected source and records proposed additions for review.",
    tone: "info",
  },
  organize_plan: {
    icon: "info",
    label: "Create Organize Plan",
    meaning:
      "Scans a Library root and records registration or organization work for review.",
    tone: "info",
  },
  refresh_plan: {
    icon: "info",
    label: "Create Refresh Plan",
    meaning:
      "Reads current file evidence and records proposed metadata refresh work for review.",
    tone: "info",
  },
  check: {
    icon: "info",
    label: "Run Check",
    meaning:
      "Inspects Library consistency and records persisted Health findings.",
    tone: "info",
  },
  apply_plan: {
    icon: "info",
    label: "Apply Plan",
    meaning:
      "Applies the recorded actions of an accepted Plan and records Run evidence.",
    tone: "info",
  },
  undo_plan: {
    icon: "info",
    label: "Create Undo Plan",
    meaning: "Creates an Undo Plan from an eligible Run for review.",
    tone: "info",
  },
} as const satisfies Record<OperationKind, OperationCatalogPresentation>;

const OPERATION_RESULT_PRESENTATIONS = {
  plan_created: {
    icon: "check",
    label: "Plan created",
    meaning: "A persisted Plan is available for inspection and review.",
    tone: "success",
  },
  registered_without_plan: {
    icon: "check",
    label: "Registered without a Plan",
    meaning:
      "The Library registration was persisted without proposed file changes.",
    tone: "success",
  },
  check_completed: {
    icon: "check",
    label: "Check completed",
    meaning: "Persisted Health findings are available for inspection.",
    tone: "success",
  },
  run_completed: {
    icon: "check",
    label: "Run completed",
    meaning: "Recorded Run evidence is available in History.",
    tone: "success",
  },
} as const satisfies Record<OperationResultKind, OperationCatalogPresentation>;

const OPERATION_STATUS_PRESENTATIONS = {
  queued: {
    icon: "info",
    label: operationCopy.queued,
    meaning: "The durable Operation was accepted and is waiting to run.",
    tone: "info",
  },
  running: {
    icon: "info",
    label: operationCopy.running,
    meaning: "The durable Operation is processing work.",
    tone: "info",
  },
  succeeded: {
    icon: "check",
    label: operationCopy.succeeded,
    meaning: "The durable Operation completed with a persisted result.",
    tone: "success",
  },
  failed: {
    icon: "warning",
    label: operationCopy.failed,
    meaning: "The durable Operation reached a terminal failed state.",
    tone: "danger",
  },
  interrupted: {
    icon: "warning",
    label: operationCopy.interrupted,
    meaning: "The worker stopped before completion could be confirmed.",
    tone: "warning",
  },
} satisfies Record<OperationStatus, OperationCatalogPresentation>;

export function operationStatusLabel(value: string) {
  return operationStatusPresentation(value).label;
}

export function operationStatusTone(value: string): OperationTone {
  return operationStatusPresentation(value).tone;
}

export function operationStatusIcon(value: string): IconName {
  return operationStatusPresentation(value).icon;
}

export function operationStatusPresentation(
  value: string,
): OperationCatalogPresentation {
  return (
    OPERATION_STATUS_PRESENTATIONS[value as OperationStatus] ?? {
      icon: "info",
      label: `${operationCopy.unknownStatus}: ${value}`,
      meaning:
        "This Operation status is not recognized by this bundled interface.",
      tone: "neutral",
    }
  );
}

export function operationKindPresentation(
  value: string,
): OperationCatalogPresentation {
  return (
    OPERATION_KIND_PRESENTATIONS[value as OperationKind] ?? {
      icon: "info",
      label: operationCopy.unknownKind(value),
      meaning:
        "This Operation kind is not recognized by this bundled interface.",
      tone: "neutral",
    }
  );
}

export function operationResultKindPresentation(
  value: string,
): OperationCatalogPresentation {
  return (
    OPERATION_RESULT_PRESENTATIONS[value as OperationResultKind] ?? {
      icon: "info",
      label: operationCopy.unknownResult(value),
      meaning:
        "This Operation result is not recognized by this bundled interface.",
      tone: "neutral",
    }
  );
}
