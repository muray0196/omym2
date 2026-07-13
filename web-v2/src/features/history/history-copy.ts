/**
 * Summary: Centralizes English copy for read-only Run history inspection.
 * Why: Keeps mutation boundaries and pending-event recovery wording consistent.
 */
export const historyCopy = {
  list: {
    eyebrow: "Inspection",
    title: "History",
    description:
      "Browse recorded Runs and durable file-mutation evidence without starting an operation.",
    searchLabel: "Search Runs",
    searchPlaceholder: "Run ID, Plan ID, Library ID, status, or error",
    statusLabel: "Run status",
    planLabel: "Plan ID",
    libraryLabel: "Library ID",
    allStatuses: "All statuses",
    reset: "Reset filters",
    loading: "Loading Run history…",
    empty: "No Runs match these filters.",
    loadMore: "Load more Runs",
    loadingMore: "Loading more Runs…",
    error: "Run history could not be loaded",
  },
  detail: {
    eyebrow: "Run evidence",
    title: "Run detail",
    back: "Back to History",
    loading: "Loading Run evidence…",
    notFound: "This Run is not available in recorded History.",
    error: "Run evidence could not be loaded",
    metadata: "Run metadata",
    capability: "Undo eligibility",
    eligible:
      "This Run is eligible for reviewed Undo planning. Execution controls are not available in inspection mode.",
    events: "File mutation evidence",
    noEvents:
      "No FileEvents were recorded. This is valid for blocked, skipped, or metadata-only work.",
    groups: "Target directory groups",
    facets: "Event status counts",
    loadMoreEvents: "Load more FileEvents",
    loadMoreGroups: "Load more groups",
  },
  pending:
    "Outcome unknown. Run Health and review this event manually; OMYM2 will not repair it automatically.",
  retry: "Try again",
  labels: {
    runId: "Run ID",
    planId: "Plan ID",
    libraryId: "Library ID",
    status: "Status",
    started: "Started",
    completed: "Completed",
    eventId: "Event ID",
    actionId: "PlanAction ID",
    source: "Source path",
    target: "Target path",
    error: "Recorded error",
    activeOperation: "Active Operation ID",
  },
  unknown: {
    status: "Unknown status",
    eventType: "Unknown event type",
    errorCode: "Unknown error code",
  },
} as const;
