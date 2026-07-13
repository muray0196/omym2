/**
 * Summary: Maps Run and FileEvent catalog values to visible labels and tones.
 * Why: Preserves unknown-value evidence without enabling operations from status.
 */
import { historyCopy } from "./history-copy";

export type EvidenceTone =
  "info" | "success" | "warning" | "danger" | "neutral";

const RUN_LABELS = {
  running: "Running",
  succeeded: "Succeeded",
  partial_failed: "Partially failed",
  failed: "Failed",
} as const;

const RUN_TONES: Record<keyof typeof RUN_LABELS, EvidenceTone> = {
  running: "info",
  succeeded: "success",
  partial_failed: "warning",
  failed: "danger",
};

const EVENT_LABELS = {
  pending: "Pending — outcome unknown",
  succeeded: "Succeeded",
  failed: "Failed",
} as const;

const EVENT_TONES: Record<keyof typeof EVENT_LABELS, EvidenceTone> = {
  pending: "warning",
  succeeded: "success",
  failed: "danger",
};

export function runStatusLabel(value: string) {
  return (
    RUN_LABELS[value as keyof typeof RUN_LABELS] ??
    `${historyCopy.unknown.status}: ${value}`
  );
}

export function runStatusTone(value: string): EvidenceTone {
  return RUN_TONES[value as keyof typeof RUN_TONES] ?? "neutral";
}

export function eventStatusLabel(value: string) {
  return (
    EVENT_LABELS[value as keyof typeof EVENT_LABELS] ??
    `${historyCopy.unknown.status}: ${value}`
  );
}

export function eventStatusTone(value: string): EvidenceTone {
  return EVENT_TONES[value as keyof typeof EVENT_TONES] ?? "neutral";
}

export function eventTypeLabel(value: string) {
  return value === "move_file"
    ? "Move file"
    : `${historyCopy.unknown.eventType}: ${value}`;
}

export function formatTimestamp(value: string | null) {
  if (value === null) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
