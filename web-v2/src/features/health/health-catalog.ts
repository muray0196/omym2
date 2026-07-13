/**
 * Summary: Maps persisted Check catalogs to visible labels and neutral unknown fallbacks.
 * Why: Makes findings understandable without branching on display text.
 */
import { healthCopy } from "./health-copy";

const ISSUE_LABELS = {
  db_file_missing: "Managed file is missing",
  unmanaged_file_exists: "Unmanaged file exists",
  content_hash_changed: "File content changed",
  metadata_hash_changed: "Metadata changed",
  current_path_differs_from_canonical_path:
    "Current path differs from canonical path",
  duplicate_candidate: "Duplicate candidate",
  plan_source_changed: "Plan source changed",
  pending_file_event_exists: "Pending FileEvent requires review",
  library_unregistered: "Library is unregistered",
  library_stale: "Library policy is stale",
  library_blocked: "Library is blocked",
} as const;

const GROUP_LABELS = {
  issue_type: "Issue type",
  severity: "Severity",
  path_root: "Path root",
  artist_album: "Artist and album",
  suggested_command: "Suggested command",
  library_id: "Library ID",
} as const;

export function issueTypeLabel(value: string) {
  return (
    ISSUE_LABELS[value as keyof typeof ISSUE_LABELS] ??
    `${healthCopy.unknown.issueType}: ${value}`
  );
}

export function groupingLabel(value: string) {
  return (
    GROUP_LABELS[value as keyof typeof GROUP_LABELS] ??
    `${healthCopy.unknown.grouping}: ${value}`
  );
}
