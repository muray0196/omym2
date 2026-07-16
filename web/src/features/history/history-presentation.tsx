/**
 * Summary: Presents Run and FileEvent statuses as text-backed evidence badges.
 * Why: Avoids color-only meaning and preserves unknown server values.
 */
import type {
  FileEventStatus,
  FileEventType,
  RunStatus,
} from "../../api/generated";
import {
  eventStatusIcon,
  eventStatusLabel,
  eventStatusTone,
  eventTypePresentation,
  runStatusIcon,
  runStatusLabel,
  runStatusTone,
  type EvidenceTone,
} from "./history-catalog";
import { Icon, type IconName } from "../../ui/icon";
import styles from "../inspection/inspection.module.css";

export function RunStatusBadge({ value }: { value: RunStatus }) {
  return (
    <EvidenceBadge
      icon={runStatusIcon(value)}
      label={runStatusLabel(value)}
      tone={runStatusTone(value)}
    />
  );
}

export function EventStatusBadge({ value }: { value: FileEventStatus }) {
  return (
    <EvidenceBadge
      label={eventStatusLabel(value)}
      icon={eventStatusIcon(value)}
      tone={eventStatusTone(value)}
    />
  );
}

export function EventTypeValue({ value }: { value: FileEventType }) {
  const presentation = eventTypePresentation(value);
  return (
    <EvidenceBadge
      icon={presentation.icon}
      label={presentation.label}
      tone={presentation.tone}
    />
  );
}

function EvidenceBadge({
  icon,
  label,
  tone,
}: {
  icon: IconName;
  label: string;
  tone: EvidenceTone;
}) {
  return (
    <span className={`${styles.badge} ${toneClass(tone)}`}>
      <Icon name={icon} />
      {label}
    </span>
  );
}

function toneClass(tone: EvidenceTone) {
  switch (tone) {
    case "success":
      return styles.success;
    case "warning":
      return styles.warningTone;
    case "danger":
      return styles.danger;
    case "info":
      return styles.info;
  }
}
