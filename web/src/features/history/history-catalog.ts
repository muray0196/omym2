/**
 * Summary: Maps Run and FileEvent catalog values to visible labels and tones.
 * Why: Preserves unknown-value evidence without enabling operations from status.
 */
import { historyCopy } from "./history-copy";
import type {
  FileEventStatus,
  FileEventType,
  RunStatus,
} from "../../api/generated";
import type { IconName } from "../../ui/icon";

export type EvidenceTone =
  "info" | "success" | "warning" | "danger" | "neutral";
export type HistoryCatalogPresentation = {
  icon: IconName;
  label: string;
  meaning: string;
  tone: EvidenceTone;
};

const RUN_STATUS_PRESENTATIONS = {
  running: {
    icon: "info",
    label: "Running",
    meaning: "The Apply run is still processing recorded PlanActions.",
    tone: "info",
  },
  succeeded: {
    icon: "check",
    label: "Succeeded",
    meaning: "The Run reached a confirmed successful terminal state.",
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
    meaning: "The Run reached a terminal failed state.",
    tone: "danger",
  },
} satisfies Record<RunStatus, HistoryCatalogPresentation>;

const EVENT_STATUS_PRESENTATIONS = {
  pending: {
    icon: "warning",
    label: "Pending — outcome unknown",
    meaning: "The mutation outcome is unknown and requires manual review.",
    tone: "warning",
  },
  succeeded: {
    icon: "check",
    label: "Succeeded",
    meaning: "The attempted file mutation completed successfully.",
    tone: "success",
  },
  failed: {
    icon: "warning",
    label: "Failed",
    meaning: "The attempted file mutation failed with recorded evidence.",
    tone: "danger",
  },
} satisfies Record<FileEventStatus, HistoryCatalogPresentation>;

const EVENT_TYPE_PRESENTATIONS = {
  move_file: {
    icon: "info",
    label: "Move file",
    meaning: "Records one attempted Library music file move.",
    tone: "info",
  },
} satisfies Record<FileEventType, HistoryCatalogPresentation>;

export function runStatusLabel(value: string) {
  return runStatusPresentation(value).label;
}

export function runStatusTone(value: string): EvidenceTone {
  return runStatusPresentation(value).tone;
}

export function runStatusIcon(value: string): IconName {
  return runStatusPresentation(value).icon;
}

export function runStatusPresentation(
  value: string,
): HistoryCatalogPresentation {
  return statusPresentationFor(value, RUN_STATUS_PRESENTATIONS);
}

export function eventStatusLabel(value: string) {
  return eventStatusPresentation(value).label;
}

export function eventStatusTone(value: string): EvidenceTone {
  return eventStatusPresentation(value).tone;
}

export function eventStatusIcon(value: string): IconName {
  return eventStatusPresentation(value).icon;
}

export function eventStatusPresentation(
  value: string,
): HistoryCatalogPresentation {
  return statusPresentationFor(value, EVENT_STATUS_PRESENTATIONS);
}

export function eventTypeLabel(value: string) {
  return eventTypePresentation(value).label;
}

export function eventTypePresentation(
  value: string,
): HistoryCatalogPresentation {
  return (
    EVENT_TYPE_PRESENTATIONS[value as FileEventType] ?? {
      icon: "info",
      label: `${historyCopy.unknown.eventType}: ${value}`,
      meaning: `No bundled presentation is available for the raw stable code ${value}.`,
      tone: "neutral",
    }
  );
}

export function formatTimestamp(value: string | null) {
  if (value === null) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function statusPresentationFor(
  value: string,
  presentations: Partial<Record<string, HistoryCatalogPresentation>>,
): HistoryCatalogPresentation {
  return (
    presentations[value] ?? {
      icon: "info",
      label: `${historyCopy.unknown.status}: ${value}`,
      meaning: `No bundled presentation is available for the raw stable code ${value}.`,
      tone: "neutral",
    }
  );
}
