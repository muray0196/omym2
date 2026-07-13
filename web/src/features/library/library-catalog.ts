/**
 * Summary: Maps Track catalog values to visible labels and neutral fallback tones.
 * Why: Keeps newer server values readable without inferring behavior from status.
 */
import { libraryCopy } from "./library-copy";
import type { LibraryStatus, TrackStatus } from "../../api/generated";
import type { IconName } from "../../ui/icon";

export type LibraryTone = "success" | "warning" | "neutral";
export type TrackTone = LibraryTone;
export type LibraryCatalogPresentation = {
  icon: IconName;
  label: string;
  meaning: string;
  tone: LibraryTone;
};

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
  artist_album: "Artist and album",
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
  return statusPresentationFor(value, LIBRARY_STATUS_PRESENTATIONS);
}

export function trackStatusTone(value: string): TrackTone {
  return trackStatusPresentation(value).tone;
}

export function trackStatusIcon(value: string): IconName {
  return trackStatusPresentation(value).icon;
}

export function trackStatusPresentation(
  value: string,
): LibraryCatalogPresentation {
  return statusPresentationFor(value, TRACK_STATUS_PRESENTATIONS);
}

export function trackGroupingLabel(value: string) {
  return labelFor(value, TRACK_GROUPING_LABELS, libraryCopy.unknown.grouping);
}

function labelFor(
  value: string,
  labels: Record<string, string>,
  unknownPrefix: string,
) {
  return labels[value] ?? `${unknownPrefix}: ${value}`;
}

function statusPresentationFor(
  value: string,
  presentations: Partial<Record<string, LibraryCatalogPresentation>>,
): LibraryCatalogPresentation {
  return (
    presentations[value] ?? {
      icon: "info",
      label: `${libraryCopy.unknown.status}: ${value}`,
      meaning: `No bundled presentation is available for the raw stable code ${value}.`,
      tone: "neutral",
    }
  );
}
