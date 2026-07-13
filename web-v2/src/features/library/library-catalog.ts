/**
 * Summary: Maps Track catalog values to visible labels and neutral fallback tones.
 * Why: Keeps newer server values readable without inferring behavior from status.
 */
import { libraryCopy } from "./library-copy";

export type TrackTone = "success" | "neutral";

const TRACK_STATUS_LABELS = {
  active: "Active",
  removed: "Removed",
} as const;

const TRACK_STATUS_TONES: Record<keyof typeof TRACK_STATUS_LABELS, TrackTone> =
  {
    active: "success",
    removed: "neutral",
  };

const TRACK_GROUPING_LABELS = {
  artist: "Artist",
  album: "Album",
  disc: "Disc",
  artist_album: "Artist and album",
} as const;

export function trackStatusLabel(value: string) {
  return labelFor(value, TRACK_STATUS_LABELS, libraryCopy.unknown.status);
}

export function trackStatusTone(value: string): TrackTone {
  return (
    TRACK_STATUS_TONES[value as keyof typeof TRACK_STATUS_TONES] ?? "neutral"
  );
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
