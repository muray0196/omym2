/**
 * Summary: Centralizes the frozen M1 performance measurement protocol.
 * Why: Prevents timing and compression settings from becoming scattered test magic.
 */
export const performanceProtocol = Object.freeze({
  measuredRuns: 5,
  warmupRuns: 1,
  gzipCommand: "gzip",
  gzipArguments: Object.freeze(["-9", "-n", "-c"]),
});
