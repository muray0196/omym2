/**
 * Summary: Presents Run and FileEvent statuses as text-backed evidence badges.
 * Why: Avoids color-only meaning and preserves unknown server values.
 */
import {
  eventStatusLabel,
  eventStatusTone,
  runStatusLabel,
  runStatusTone,
  type EvidenceTone,
} from "./history-catalog";
import styles from "../inspection/inspection.module.css";

export function RunStatusBadge({ value }: { value: string }) {
  return (
    <EvidenceBadge label={runStatusLabel(value)} tone={runStatusTone(value)} />
  );
}

export function EventStatusBadge({ value }: { value: string }) {
  return (
    <EvidenceBadge
      label={eventStatusLabel(value)}
      tone={eventStatusTone(value)}
    />
  );
}

function EvidenceBadge({ label, tone }: { label: string; tone: EvidenceTone }) {
  return <span className={`${styles.badge} ${toneClass(tone)}`}>{label}</span>;
}

function toneClass(tone: EvidenceTone) {
  if (tone === "success") return styles.success;
  if (tone === "warning") return styles.warningTone;
  if (tone === "danger") return styles.danger;
  if (tone === "info") return styles.info;
  return styles.neutral;
}
