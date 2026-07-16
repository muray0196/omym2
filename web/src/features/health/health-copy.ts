/**
 * Summary: Centralizes English copy for persisted Health inspection.
 * Why: Keeps freshness, execution, and manual-review guidance consistent.
 */
export const healthCopy = {
  eyebrow: "Persisted Check",
  title: "Health",
  description:
    "Inspect the latest saved Check findings. Opening this page does not scan the filesystem.",
  freshness: "Findings checked",
  neverChecked: "No completed Check has been persisted for this scope.",
  searchLabel: "Search findings",
  searchPlaceholder: "Library ID, path, Track ID, Plan ID, or detail…",
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
  facets: "Issue type counts",
  groups: "Finding groups",
  findings: "Persisted findings",
  companionAsset: "Companion asset",
  pending:
    "Mutation outcome is unknown. Review History and the filesystem manually; no automatic repair is available.",
  unprocessedEvidence:
    "This finding represents broken durable unprocessed-file evidence. Review History and the filesystem manually; no automatic refresh or Add repair is safe.",
  openHistory: "Open History",
  run: {
    title: "Run Check",
    description:
      "Scan current state and replace the selected Library's persisted findings.",
    libraryLabel: "Check scope",
    safety:
      "Check reads the filesystem and persists diagnostics. It does not change Library music files or managed Tracks.",
    submit: "Run Check",
    starting: "Starting Check…",
    completed: (issueCount: number, runCount: number) =>
      `Saved ${issueCount} findings across ${runCount} Check runs. Persisted Health has been refreshed.`,
  },
} as const;
