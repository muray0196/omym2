/**
 * Summary: Centralizes product-default-language durable Operation copy.
 * Why: Keeps progress, disconnection, and terminal announcements consistent.
 */
export const operationCopy = {
  accepted: "Operation accepted. Waiting for progress.",
  queued: "Queued",
  running: "Running",
  succeeded: "Completed",
  failed: "Failed",
  interrupted: "Interrupted",
  disconnected: "Connection lost. OMYM2 will keep polling this Operation.",
  progress: "Operation progress",
  units: (completed: number, total: number) =>
    `${completed} of ${total} units complete`,
  unknownStage: "Working",
  expired:
    "This Operation result has expired. Inspect the current Plans, History, or Health state before starting new work.",
  unexpected: "The Operation status could not be read.",
  planCreated: "Plan created. Opening Plan review.",
  registered: (trackCount: number) =>
    `Library registered with ${trackCount} tracks.`,
  checkCompleted: (issueCount: number) =>
    `Check completed with ${issueCount} findings.`,
  associations: "Related persisted state",
  inspectPlan: "Inspect related Plan",
  inspectRun: "Inspect related Run",
  inspectLibrary: "Inspect related Library",
  inspectHealth: "Inspect persisted Health",
  recoveryEyebrow: "Durable work",
  recoveryTitle: "Operation recovery",
  recoveryDescription:
    "This address reloads persisted progress without resending the original mutation.",
  loading: "Loading Operation…",
  pollingUnavailable:
    "Startup polling policy is unavailable. Restore the local service and reload this Operation.",
  expiredTitle: "Operation result expired",
  notFoundTitle: "Operation not found",
  readErrorTitle: "Operation could not be loaded",
  retryRead: "Try reading again",
} as const;
