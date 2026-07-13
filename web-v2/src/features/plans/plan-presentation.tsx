/**
 * Summary: Presents Plan catalog values with explicit labels and neutral unknown fallbacks.
 * Why: Keeps recorded status evidence understandable without inferring any allowed operation.
 */
import {
  actionStatusLabel,
  actionStatusTone,
  planStatusLabel,
  planStatusTone,
  type PlanTone,
} from "./plan-catalog";
import styles from "./plan-inspection.module.css";

export function PlanStatusBadge({ value }: { value: string }) {
  const label = planStatusLabel(value);
  const tone = planStatusTone(value);

  return <StatusBadge label={label} rawValue={value} tone={tone} />;
}

export function ActionStatusBadge({ value }: { value: string }) {
  const label = actionStatusLabel(value);
  const tone = actionStatusTone(value);

  return <StatusBadge label={label} rawValue={value} tone={tone} />;
}

function StatusBadge({
  label,
  rawValue,
  tone,
}: {
  label: string;
  rawValue: string;
  tone: PlanTone;
}) {
  return (
    <span
      className={`${styles.statusBadge} ${toneClassName(tone)}`}
      data-status={rawValue}
    >
      {label}
    </span>
  );
}

function toneClassName(tone: PlanTone) {
  switch (tone) {
    case "info":
      return styles.toneInfo;
    case "success":
      return styles.toneSuccess;
    case "warning":
      return styles.toneWarning;
    case "danger":
      return styles.toneDanger;
    case "neutral":
      return styles.toneNeutral;
  }
}
