/**
 * Summary: Renders the shared closed-catalog status/evidence badge with an icon, label, and tone.
 * Why: Collapses duplicated tone-to-badge implementations into one accessible primitive.
 */
import { Icon, type IconName } from "../icon";
import { toneClassName, type Tone } from "./tone";
import styles from "./catalog-badge.module.css";

export function CatalogBadge({
  icon,
  label,
  rawValue,
  tone,
}: {
  icon: IconName;
  label: string;
  rawValue?: string;
  tone: Tone;
}) {
  return (
    <span
      className={`${styles.badge} ${toneClassName(tone)}`}
      data-status={rawValue}
    >
      <Icon name={icon} />
      {label}
    </span>
  );
}
