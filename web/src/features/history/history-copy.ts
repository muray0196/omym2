/**
 * Summary: Centralizes English copy for Run evidence and reviewed Undo planning.
 * Why: Keeps mutation boundaries, capability reasons, and pending-event recovery consistent.
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
    events: "File mutation evidence",
    noEvents:
      "No FileEvents were recorded. This is valid for blocked, skipped, or metadata-only work.",
    groups: "Target directory groups",
    facets: "Event status counts",
  },
  undo: {
    title: "Undo planning",
    description:
      "Create a new Undo Plan from durable Run evidence, then review every recorded reversal before Apply.",
    create: "Create Undo Plan",
    starting: "Starting Undo planning…",
    activeOperation: "Recover active Operation",
    noBootstrap:
      "Undo planning needs the local startup token. Restore the service and reload this Run.",
    error: "Undo Plan could not be started",
    planResult: "Open Undo Plan review",
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
