/**
 * Summary: Presents Track status and persisted values with explicit accessible fallbacks.
 * Why: Keeps unknown catalog values and missing metadata readable without status inference.
 */
import type { ReactNode } from "react";

import { trackStatusLabel, trackStatusTone } from "./library-catalog";
import styles from "./library-inspection.module.css";

export function TrackStatusBadge({ value }: { value: string }) {
  const tone = trackStatusTone(value);
  return (
    <span
      className={`${styles.statusBadge} ${tone === "success" ? styles.toneSuccess : styles.toneNeutral}`}
      data-status={value}
    >
      {trackStatusLabel(value)}
    </span>
  );
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
