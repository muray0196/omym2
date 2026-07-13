/**
 * Summary: Centralizes product-default-language copy for the frozen route map.
 * Why: Keeps Overview and not-found wording consistent without embedded route copy.
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
  notFound: {
    eyebrow: "Not found",
    title: "This route does not exist",
    description: "Check the address or return to the operations overview.",
    action: "Return to overview",
  },
} as const;
