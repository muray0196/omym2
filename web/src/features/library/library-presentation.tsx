/**
 * Summary: Presents Track status and persisted values with explicit accessible fallbacks.
 * Why: Keeps unknown catalog values and missing metadata readable without status inference.
 */
import type { ReactNode } from "react";

import type { LibraryStatus, TrackStatus } from "../../api/generated";
import { CatalogBadge } from "../../ui/primitives/catalog-badge";
import {
  libraryStatusIcon,
  libraryStatusLabel,
  libraryStatusTone,
  trackStatusIcon,
  trackStatusLabel,
  trackStatusTone,
} from "./library-catalog";
import styles from "./library-inspection.module.css";

export function LibraryStatusBadge({ value }: { value: LibraryStatus }) {
  return (
    <CatalogBadge
      icon={libraryStatusIcon(value)}
      label={libraryStatusLabel(value)}
      rawValue={value}
      tone={libraryStatusTone(value)}
    />
  );
}

export function TrackStatusBadge({ value }: { value: TrackStatus }) {
  return (
    <CatalogBadge
      icon={trackStatusIcon(value)}
      label={trackStatusLabel(value)}
      rawValue={value}
      tone={trackStatusTone(value)}
    />
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
