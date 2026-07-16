/**
 * Summary: Maps closed persisted Check catalogs to visible labels and tones.
 * Why: Gives every coordinated generated enum value an exhaustive presentation.
 */
import type { CheckIssueGrouping, CheckIssueType } from "../../api/generated";
import { catalogValueOrThrow } from "../../ui/catalog";
import type { IconName } from "../../ui/icon";

export type HealthTone = "warning" | "danger";
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
  companion_file_missing: {
    icon: "warning",
    label: "Companion file is missing",
    meaning:
      "A managed companion asset's recorded current path is missing on disk.",
    tone: "danger",
  },
  companion_content_hash_changed: {
    icon: "warning",
    label: "Companion content changed",
    meaning:
      "A managed companion file no longer matches its recorded content hash.",
    tone: "danger",
  },
  companion_current_path_differs_from_canonical_path: {
    icon: "warning",
    label: "Companion path differs from canonical path",
    meaning: "A managed companion asset is not stored at its canonical path.",
    tone: "warning",
  },
  companion_owner_missing: {
    icon: "warning",
    label: "Companion owner is missing",
    meaning:
      "A managed companion asset no longer has its recorded owning Track.",
    tone: "danger",
  },
  unmanaged_companion_exists: {
    icon: "warning",
    label: "Unmanaged companion exists",
    meaning:
      "A companion file exists without a managed companion-asset record.",
    tone: "warning",
  },
  failed_companion_source_exists: {
    icon: "warning",
    label: "Failed companion source remains",
    meaning:
      "A definitively failed companion source remains eligible for a new reviewed Plan.",
    tone: "danger",
  },
  unprocessed_file_missing: {
    icon: "warning",
    label: "Unprocessed file is missing",
    meaning:
      "A reviewed unprocessed-file target is missing; inspect its durable History before taking action.",
    tone: "danger",
  },
  unprocessed_content_hash_changed: {
    icon: "warning",
    label: "Unprocessed file content changed",
    meaning:
      "A reviewed unprocessed-file target no longer matches its recorded hash; inspect its durable History.",
    tone: "danger",
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
} as const satisfies Record<CheckIssueGrouping, string>;

export function issueTypeLabel(value: string) {
  return issueTypePresentation(value).label;
}

export function issueTypePresentation(
  value: string,
): HealthCatalogPresentation {
  return catalogValueOrThrow("Check issue type", value, ISSUE_PRESENTATIONS);
}

export function groupingLabel(value: string) {
  return catalogValueOrThrow("Check grouping", value, GROUP_LABELS);
}

export function healthGroupValueLabel(
  groupBy: CheckIssueGrouping,
  key: string,
  serverLabel: string,
) {
  return groupBy === "issue_type"
    ? catalogValueOrThrow("Check issue type", key, ISSUE_PRESENTATIONS).label
    : serverLabel;
}
