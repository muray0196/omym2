/**
 * Summary: Centralizes product-default-language Bootstrap and recovery copy.
 * Why: Keeps connection and degraded-state wording consistent across the shell.
 */
export const bootstrapCopy = {
  loading: "Connecting to the local OMYM2 service…",
  connected: "Local service connected",
  noLibrary: "No active Library is selected.",
  degraded: "OMYM2 needs attention before all operations are available.",
  unexpected: "OMYM2 could not load its startup state.",
  disconnected: "The local OMYM2 service is unavailable.",
  disconnectedDetail: "Check that the local server is running, then try again.",
  missingRecoveryData: "Bootstrap did not provide recovery data.",
  retry: "Try again",
  diagnosticsLabel: "Recovery diagnostics",
  remediationsLabel: "Recovery actions",
  activeOperation: "An accepted Operation is still active.",
  resumeOperation: "Resume Operation progress",
} as const;
