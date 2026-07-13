/**
 * Summary: Centralizes the installed-package performance protocol and enforced budgets.
 * Why: Keeps M2 timing and bundle-size gates aligned with the frozen frontend contract.
 */
export const performanceProtocol = Object.freeze({
  measuredRuns: 5,
  warmupRuns: 1,
  gzipCommand: "gzip",
  gzipArguments: Object.freeze(["-9", "-n", "-c"]),
  maximumInteractiveShellMs: 1000,
  maximumInitialJavascriptBytes: 250000,
});
