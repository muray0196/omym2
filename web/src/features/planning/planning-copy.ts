/**
 * Summary: Centralizes product-default-language planning form copy.
 * Why: Keeps path scope, safety boundaries, and recovery wording consistent.
 */
export const planningCopy = {
  add: {
    eyebrow: "Create Plan",
    title: "Add music",
    description:
      "Scan Incoming or one explicit source directory and create a reviewable Add Plan. No music files move in this step.",
    sourceLabel: "Source directory (optional)",
    sourceHint: "Leave blank to use the configured Incoming directory.",
    submit: "Scan and create Plan",
  },
  organize: {
    eyebrow: "Create Plan",
    title: "Organize Library",
    description:
      "Scan one explicit Library root for registration or reconciliation. OMYM2 either creates a reviewable Plan or registers an already organized Library.",
    rootLabel: "Library root",
    rootHint: "Enter the full path to the Library directory.",
    submit: "Scan Library",
  },
  refresh: {
    eyebrow: "Create Plan",
    title: "Refresh metadata",
    description:
      "Re-read metadata for one file, one directory, or the entire selected Library and create a reviewable Refresh Plan.",
    scopeLabel: "Refresh scope",
    pathLabel: "File or directory path",
    pathHint:
      "The selected scope determines whether this path is treated as one file or one directory.",
    scopes: {
      file: "One file",
      directory: "One directory",
      all: "Entire Library",
    },
    submit: "Create Refresh Plan",
  },
  disabled: "Operations are currently unavailable.",
  failure: "The Operation could not be started.",
  noBootstrap:
    "Startup state is unavailable. Restore the local service before starting work.",
  noFileMutation:
    "Planning scans and persists review evidence only. Library music files are not changed.",
  planLink: "Review created Plan",
  libraryLink: "Open Library",
} as const;
