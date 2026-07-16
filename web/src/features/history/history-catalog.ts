/**
 * Summary: Maps closed Run and FileEvent catalogs to visible labels and tones.
 * Why: Gives every coordinated generated enum value an exhaustive presentation.
 */
import type {
  FileEventStatus,
  FileEventType,
  RunStatus,
} from "../../api/generated";
import type { IconName } from "../../ui/icon";
import { catalogValueOrThrow } from "../../ui/catalog";

export type EvidenceTone = "info" | "success" | "warning" | "danger";
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
  move_lyrics_file: {
    icon: "info",
    label: "Move lyrics file",
    meaning: "Records one attempted managed lyrics-file move.",
    tone: "info",
  },
  move_artwork_file: {
    icon: "info",
    label: "Move artwork file",
    meaning: "Records one attempted managed artwork-file move.",
    tone: "info",
  },
  move_unprocessed_file: {
    icon: "info",
    label: "Move unprocessed file",
    meaning: "Records one attempted reviewed unprocessed-file move.",
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
  return catalogValueOrThrow("Run status", value, RUN_STATUS_PRESENTATIONS);
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
  return catalogValueOrThrow(
    "FileEvent status",
    value,
    EVENT_STATUS_PRESENTATIONS,
  );
}

export function eventTypePresentation(
  value: string,
): HistoryCatalogPresentation {
  return catalogValueOrThrow("FileEvent type", value, EVENT_TYPE_PRESENTATIONS);
}

export function formatTimestamp(value: string | null) {
  if (value === null) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
