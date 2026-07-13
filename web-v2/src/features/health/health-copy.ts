/**
 * Summary: Centralizes English copy for persisted Health inspection.
 * Why: Keeps freshness and manual-review guidance consistent without exposing Check execution.
 */
export const healthCopy = {
  eyebrow: "Persisted Check",
  title: "Health",
  description:
    "Inspect the latest saved Check findings. Opening this page does not scan the filesystem.",
  freshness: "Findings checked",
  neverChecked: "No completed Check has been persisted for this scope.",
  searchLabel: "Search findings",
  searchPlaceholder: "Library ID, path, Track ID, Plan ID, or detail",
  issueTypeLabel: "Issue type",
  groupingLabel: "Group findings by",
  libraryLabel: "Library ID",
  allIssueTypes: "All issue types",
  reset: "Reset filters",
  clearGroup: "Clear group selection",
  selectedGroup: "Selected group",
  loading: "Loading persisted Health findings…",
  empty: "No persisted findings match these filters.",
  error: "Persisted Health findings could not be loaded",
  loadMore: "Load more findings",
  loadMoreGroups: "Load more groups",
  retry: "Try again",
  facets: "Issue type counts",
  groups: "Finding groups",
  findings: "Persisted findings",
  pending:
    "Mutation outcome is unknown. Review History and the filesystem manually; no automatic repair is available.",
  unknown: { issueType: "Unknown issue type", grouping: "Unknown grouping" },
} as const;
