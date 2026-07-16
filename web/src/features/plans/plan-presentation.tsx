/**
 * Summary: Presents closed Plan catalog values with explicit labels and tones.
 * Why: Keeps recorded status evidence understandable without inferring any allowed operation.
 */
import type {
  ActionStatus,
  ActionType,
  PlanActionReason,
  PlanStatus,
  PlanType,
} from "../../api/generated";
import {
  actionTypePresentation,
  actionStatusIcon,
  actionStatusLabel,
  actionStatusTone,
  planTypePresentation,
  planStatusIcon,
  planStatusLabel,
  planStatusTone,
  reasonPresentation,
  type PlanTone,
} from "./plan-catalog";
import { Icon, type IconName } from "../../ui/icon";
import styles from "./plan-inspection.module.css";

export function PlanStatusBadge({ value }: { value: PlanStatus }) {
  const label = planStatusLabel(value);
  const tone = planStatusTone(value);

  return (
    <StatusBadge
      icon={planStatusIcon(value)}
      label={label}
      rawValue={value}
      tone={tone}
    />
  );
}

export function ActionStatusBadge({ value }: { value: ActionStatus }) {
  const label = actionStatusLabel(value);
  const tone = actionStatusTone(value);

  return (
    <StatusBadge
      icon={actionStatusIcon(value)}
      label={label}
      rawValue={value}
      tone={tone}
    />
  );
}

export function PlanTypeValue({ value }: { value: PlanType }) {
  return <CatalogValue presentation={planTypePresentation(value)} />;
}

export function ActionTypeValue({ value }: { value: ActionType }) {
  return <CatalogValue presentation={actionTypePresentation(value)} />;
}

export function ReasonValue({ value }: { value: PlanActionReason | null }) {
  if (value === null) return <>—</>;
  return <CatalogValue presentation={reasonPresentation(value)} />;
}

function CatalogValue({
  presentation,
}: {
  presentation: { icon: IconName; label: string; tone: PlanTone };
}) {
  return (
    <span
      className={`${styles.catalogValue} ${toneClassName(presentation.tone)}`}
    >
      <Icon name={presentation.icon} />
      {presentation.label}
    </span>
  );
}

function StatusBadge({
  icon,
  label,
  rawValue,
  tone,
}: {
  icon: IconName;
  label: string;
  rawValue: string;
  tone: PlanTone;
}) {
  return (
    <span
      className={`${styles.statusBadge} ${toneClassName(tone)}`}
      data-status={rawValue}
    >
      <Icon name={icon} />
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
