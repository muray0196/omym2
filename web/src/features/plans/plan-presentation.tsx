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
import { CatalogBadge } from "../../ui/primitives/catalog-badge";
import { toneClassName } from "../../ui/primitives/tone";
import styles from "./plan-inspection.module.css";

export function PlanStatusBadge({ value }: { value: PlanStatus }) {
  const label = planStatusLabel(value);
  const tone = planStatusTone(value);

  return (
    <CatalogBadge
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
    <CatalogBadge
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
