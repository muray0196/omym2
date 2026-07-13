/**
 * Summary: Presents Track status and persisted values with explicit accessible fallbacks.
 * Why: Keeps unknown catalog values and missing metadata readable without status inference.
 */
import type { ReactNode } from "react";

import { Icon, type IconName } from "../../ui/icon";
import {
  libraryStatusIcon,
  libraryStatusLabel,
  libraryStatusTone,
  trackStatusIcon,
  trackStatusLabel,
  trackStatusTone,
  type LibraryTone,
} from "./library-catalog";
import styles from "./library-inspection.module.css";

export function LibraryStatusBadge({ value }: { value: string }) {
  return (
    <StatusBadge
      icon={libraryStatusIcon(value)}
      label={libraryStatusLabel(value)}
      rawValue={value}
      tone={libraryStatusTone(value)}
    />
  );
}

export function TrackStatusBadge({ value }: { value: string }) {
  return (
    <StatusBadge
      icon={trackStatusIcon(value)}
      label={trackStatusLabel(value)}
      rawValue={value}
      tone={trackStatusTone(value)}
    />
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
  tone: LibraryTone;
}) {
  return (
    <span
      className={`${styles.statusBadge} ${toneClass(tone)}`}
      data-status={rawValue}
    >
      <Icon name={icon} />
      {label}
    </span>
  );
}

function toneClass(tone: LibraryTone) {
  if (tone === "success") return styles.toneSuccess;
  if (tone === "warning") return styles.toneWarning;
  return styles.toneNeutral;
}

export function DefinitionItem({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={mono ? styles.monoValue : undefined}>{children}</dd>
    </div>
  );
}
