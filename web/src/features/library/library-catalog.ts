/**
 * Summary: Maps closed Library and Track catalogs to visible labels and tones.
 * Why: Keeps every coordinated generated enum value exhaustively presented.
 */
import type { LibraryStatus, TrackStatus } from "../../api/generated";
import {
  catalogValueOrThrow,
  type CatalogPresentation,
} from "../../ui/catalog";
import type { IconName } from "../../ui/icon";

export type LibraryTone = "success" | "warning" | "neutral";
type LibraryCatalogPresentation = CatalogPresentation<LibraryTone>;

const LIBRARY_STATUS_PRESENTATIONS = {
  registered: {
    icon: "check",
    label: "Registered",
    meaning: "The Library is registered for managed operations.",
    tone: "success",
  },
  unregistered: {
    icon: "info",
    label: "Unregistered",
    meaning: "The Library has not completed registration.",
    tone: "neutral",
  },
  stale: {
    icon: "warning",
    label: "Stale",
    meaning: "The recorded Library policy no longer matches current policy.",
    tone: "warning",
  },
  blocked: {
    icon: "warning",
    label: "Blocked",
    meaning:
      "The Library cannot start operations until its blocker is resolved.",
    tone: "warning",
  },
} satisfies Record<LibraryStatus, LibraryCatalogPresentation>;

const TRACK_STATUS_PRESENTATIONS = {
  active: {
    icon: "check",
    label: "Active",
    meaning: "The Track is active in the managed Library inventory.",
    tone: "success",
  },
  removed: {
    icon: "close",
    label: "Removed",
    meaning: "The Track is retained as removed recorded evidence.",
    tone: "neutral",
  },
} satisfies Record<TrackStatus, LibraryCatalogPresentation>;

const TRACK_GROUPING_LABELS = {
  artist: "Artist",
  album: "Album",
  disc: "Disc",
} as const;

export function trackStatusLabel(value: string) {
  return trackStatusPresentation(value).label;
}

export function libraryStatusLabel(value: string) {
  return libraryStatusPresentation(value).label;
}

export function libraryStatusTone(value: string): LibraryTone {
  return libraryStatusPresentation(value).tone;
}

export function libraryStatusIcon(value: string): IconName {
  return libraryStatusPresentation(value).icon;
}

export function libraryStatusPresentation(
  value: string,
): LibraryCatalogPresentation {
  return catalogValueOrThrow(
    "Library status",
    value,
    LIBRARY_STATUS_PRESENTATIONS,
  );
}

export function trackStatusTone(value: string): LibraryTone {
  return trackStatusPresentation(value).tone;
}

export function trackStatusIcon(value: string): IconName {
  return trackStatusPresentation(value).icon;
}

export function trackStatusPresentation(
  value: string,
): LibraryCatalogPresentation {
  return catalogValueOrThrow("Track status", value, TRACK_STATUS_PRESENTATIONS);
}

export function trackGroupingLabel(value: string) {
  return catalogValueOrThrow("Track grouping", value, TRACK_GROUPING_LABELS);
}
