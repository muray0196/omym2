/**
 * Summary: Centralizes product-default-language copy for the frozen route map.
 * Why: Keeps evaluation placeholders explicit without scattering unfinished feature wording.
 */
export const routeCopy = {
  overview: {
    title: "Operations overview",
    eyebrow: "Inspection console",
    description:
      "Review current readiness, ready Plans, recent execution, and persisted Health evidence.",
    readinessTitle: "Readiness",
    readinessBody: "No current Library path is available.",
    noLibrary: "No active Library",
    plansTitle: "Ready Plans",
    historyTitle: "Recent execution",
    healthTitle: "Health",
    openPlans: "Open Plans",
    openHistory: "Open History",
    openHealth: "Open Health",
    loading: "Loading persisted state…",
    noReadyPlans: "No ready Plans",
    readyPlans: "ready Plans",
    noRuns: "No Runs have been recorded",
    noHealthIssues: "No persisted Health issues",
    healthIssues: "persisted issues",
    errorTitle: "Overview data could not be loaded",
    errorBody:
      "Readiness remains available. Retry the persisted inspection requests.",
    retry: "Try again",
    plansError: "Ready Plans could not be loaded.",
    historyError: "Recent History could not be loaded.",
    healthError: "Persisted Health could not be loaded.",
  },
  plans: {
    title: "Plans",
    description:
      "Browse and review generated Plans. Data integration arrives with the inspection milestone.",
  },
  addPlan: {
    title: "Add music",
    description:
      "The Add planning flow will scan a source and create a reviewable Plan.",
  },
  organizePlan: {
    title: "Organize library",
    description:
      "The Organize planning flow will register or reconcile the selected Library.",
  },
  refreshPlan: {
    title: "Refresh metadata",
    description:
      "The Refresh planning flow will target one file, a directory, or the entire Library.",
  },
  planDetail: {
    title: "Plan review",
    description:
      "Plan actions, summaries, and backend-authoritative capabilities will appear here.",
  },
  library: {
    title: "Library",
    description:
      "Search and group persisted Tracks without reading Library files in the browser.",
  },
  trackDetail: {
    title: "Track detail",
    description:
      "Persisted metadata, identity, hashes, and History links will appear here.",
  },
  health: {
    title: "Health",
    description:
      "The latest persisted Check findings will appear here without GET-time filesystem work.",
  },
  history: {
    title: "History",
    description: "Runs and durable file-mutation evidence will appear here.",
  },
  runDetail: {
    title: "Run detail",
    description:
      "Run results, FileEvents, and backend-authoritative Undo eligibility will appear here.",
  },
  settings: {
    title: "Settings",
    description:
      "Configuration recovery, validation, preview, and revision-safe saving will appear here.",
  },
  placeholderLabel: "Milestone preview",
  notFound: {
    eyebrow: "Not found",
    title: "This route does not exist",
    description: "Check the address or return to the operations overview.",
    action: "Return to overview",
  },
} as const;
