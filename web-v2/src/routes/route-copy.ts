/**
 * Summary: Centralizes product-default-language copy for the frozen route map.
 * Why: Keeps evaluation placeholders explicit without scattering unfinished feature wording.
 */
export const routeCopy = {
  overview: {
    title: "Operations overview",
    eyebrow: "Foundation",
    description:
      "The local operations console is ready for typed backend integration.",
  },
  overviewCards: [
    {
      title: "Readiness",
      body: "Bootstrap will report configuration and library readiness here.",
    },
    {
      title: "Plan review",
      body: "Plans remain reviewable evidence before any execution is offered.",
    },
    {
      title: "History and health",
      body: "Persisted Runs and Checks will provide verification after each operation.",
    },
  ],
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
