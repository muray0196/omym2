/**
 * Summary: Maps persisted Check catalogs to visible labels and neutral unknown fallbacks.
 * Why: Makes findings understandable without branching on display text.
 */
import { healthCopy } from "./health-copy";
import type { CheckIssueType } from "../../api/generated";
import type { IconName } from "../../ui/icon";

export type HealthTone = "warning" | "danger" | "neutral";
export type HealthCatalogPresentation = {
  icon: IconName;
  label: string;
  meaning: string;
  tone: HealthTone;
};

const ISSUE_PRESENTATIONS = {
  db_file_missing: {
    icon: "warning",
    label: "Managed file is missing",
    meaning: "A managed Track's recorded current path is missing on disk.",
    tone: "danger",
  },
  unmanaged_file_exists: {
    icon: "warning",
    label: "Unmanaged file exists",
    meaning: "A Library music file exists without a managed Track record.",
    tone: "warning",
  },
  content_hash_changed: {
    icon: "warning",
    label: "File content changed",
    meaning: "A managed file no longer matches its recorded content hash.",
    tone: "danger",
  },
  metadata_hash_changed: {
    icon: "warning",
    label: "Metadata changed",
    meaning: "A managed file no longer matches its recorded metadata hash.",
    tone: "warning",
  },
  current_path_differs_from_canonical_path: {
    icon: "warning",
    label: "Current path differs from canonical path",
    meaning: "A managed Track is not stored at its current canonical path.",
    tone: "warning",
  },
  duplicate_candidate: {
    icon: "warning",
    label: "Duplicate candidate",
    meaning: "Multiple files are candidates for the same recorded content.",
    tone: "warning",
  },
  plan_source_changed: {
    icon: "warning",
    label: "Plan source changed",
    meaning: "A Plan source no longer matches the state recorded at planning.",
    tone: "warning",
  },
  pending_file_event_exists: {
    icon: "warning",
    label: "Pending FileEvent requires review",
    meaning: "A mutation outcome is unknown and requires manual review.",
    tone: "warning",
  },
  library_unregistered: {
    icon: "warning",
    label: "Library is unregistered",
    meaning: "The Library has not completed registration.",
    tone: "warning",
  },
  library_stale: {
    icon: "warning",
    label: "Library policy is stale",
    meaning: "The Library's recorded policy no longer matches current policy.",
    tone: "warning",
  },
  library_blocked: {
    icon: "warning",
    label: "Library is blocked",
    meaning:
      "The Library cannot start operations until its blocker is resolved.",
    tone: "warning",
  },
} satisfies Record<CheckIssueType, HealthCatalogPresentation>;

const GROUP_LABELS = {
  issue_type: "Issue type",
  severity: "Severity",
  path_root: "Path root",
  artist_album: "Artist and album",
  suggested_command: "Suggested command",
  library_id: "Library ID",
} as const;

export function issueTypeLabel(value: string) {
  return issueTypePresentation(value).label;
}

export function issueTypePresentation(
  value: string,
): HealthCatalogPresentation {
  return (
    ISSUE_PRESENTATIONS[value as CheckIssueType] ?? {
      icon: "info",
      label: `${healthCopy.unknown.issueType}: ${value}`,
      meaning: `No bundled presentation is available for the raw stable code ${value}.`,
      tone: "neutral",
    }
  );
}

export function groupingLabel(value: string) {
  return (
    GROUP_LABELS[value as keyof typeof GROUP_LABELS] ??
    `${healthCopy.unknown.grouping}: ${value}`
  );
}

export function healthGroupValueLabel(
  groupBy: string,
  key: string,
  serverLabel: string,
) {
  return groupBy === "issue_type" ? issueTypeLabel(key) : serverLabel;
}
