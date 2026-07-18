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
} from "./history-catalog";
import { CatalogBadge } from "../../ui/primitives/catalog-badge";

export function RunStatusBadge({ value }: { value: RunStatus }) {
  return (
    <CatalogBadge
      icon={runStatusIcon(value)}
      label={runStatusLabel(value)}
      tone={runStatusTone(value)}
    />
  );
}

export function EventStatusBadge({ value }: { value: FileEventStatus }) {
  return (
    <CatalogBadge
      label={eventStatusLabel(value)}
      icon={eventStatusIcon(value)}
      tone={eventStatusTone(value)}
    />
  );
}

export function EventTypeValue({ value }: { value: FileEventType }) {
  const presentation = eventTypePresentation(value);
  return (
    <CatalogBadge
      icon={presentation.icon}
      label={presentation.label}
      tone={presentation.tone}
    />
  );
}
