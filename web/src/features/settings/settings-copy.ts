/**
 * Summary: Centralizes English copy and sample values for the Settings workflow.
 * Why: Keeps recovery, review, conflict, and save language consistent across form states.
 */
import type { PathPreviewRequest } from "../../api/generated";

export const settingsCopy = {
  eyebrow: "Configuration",
  title: "Settings",
  description:
    "Edit paths and planning policy, review the backend validation diff, then save against the revision you opened.",
  loading: "Loading Settings…",
  loadError: "Settings could not be loaded",
  retry: "Try again",
  recoveryTitle: "Configuration recovery",
  recoveryBody:
    "The persisted configuration is invalid. This recovery draft can replace it after backend validation succeeds.",
  revisionLabel: "Editing revision",
  pathsTitle: "Paths",
  libraryPath: "Library path",
  incomingPath: "Incoming path",
  pathHelp:
    "Enter paths directly. The backend validates them; this browser does not inspect the filesystem.",
  pathPolicyTitle: "Path policy",
  template: "Path template",
  placeholders: "Available placeholders",
  unknownArtist: "Unknown artist label",
  unknownAlbum: "Unknown album label",
  sanitize: "Sanitize rendered path components",
  maxFilenameLength: "Maximum filename length",
  discNumberStyle: "Disc number style",
  discNumberCondition: "Disc number condition",
  artistIdsTitle: "Artist IDs",
  artistIdsHelp:
    "Generation changes only this draft. Review and save before generated entries become persistent.",
  artistIdMaxLength: "Maximum artist ID length",
  artistIdFallback: "Fallback artist ID",
  entriesTitle: "Saved artist ID entries",
  noEntries: "No artist ID entries are in this draft.",
  sourceArtist: "Source artist",
  artistId: "Artist ID",
  removeEntry: "Remove",
  manualSource: "New source artist",
  manualId: "New artist ID",
  addEntry: "Add entry",
  artistNames: "Artist names to generate",
  artistNamesHelp: "Enter one source artist per line.",
  overwrite: "Regenerate existing entries",
  generate: "Generate and merge into draft",
  generating: "Generating artist IDs…",
  metadataTitle: "Metadata policy",
  preferAlbumArtist: "Prefer album artist",
  requireTitle: "Require title",
  requireArtist: "Require artist",
  requireAlbum: "Require album",
  albumYearResolution: "Album year resolution",
  collisionTitle: "Collision policy",
  targetExists: "When a target exists",
  duplicateHash: "When a duplicate hash exists",
  missingMetadata: "When required metadata is missing",
  previewTitle: "Path preview",
  previewBody:
    "Preview is self-contained: it uses this draft and the sample metadata below without reading persisted state.",
  sampleArtist: "Sample artist",
  sampleAlbumArtist: "Sample album artist",
  sampleAlbum: "Sample album",
  sampleTitle: "Sample title",
  sampleYear: "Sample year",
  sampleDisc: "Sample disc number",
  sampleTrack: "Sample track number",
  sampleExtension: "Sample file extension",
  updatePreview: "Update preview",
  previewing: "Updating preview…",
  previewUnavailable: "No path could be rendered.",
  review: "Review changes",
  reviewing: "Reviewing changes…",
  reviewTitle: "Validation and changes",
  reviewNeeded: "Review this draft before saving.",
  reviewOutdated:
    "The draft changed after validation. Review it again before saving.",
  valid: "Backend validation passed.",
  invalid: "Backend validation found fields that need attention.",
  validationTitle: "Settings validation failed",
  noChanges:
    "The reviewed draft has no changes from the persisted configuration.",
  field: "Field",
  before: "Before",
  after: "After",
  validationErrors: "Validation errors",
  save: "Save Settings",
  saving: "Saving Settings…",
  saved: "Settings saved.",
  savedBody:
    "The configuration was atomically replaced at the reviewed revision.",
  saveUnavailable:
    "Saving is unavailable in the current runtime state. Validation and preview remain available.",
  conflictTitle: "Configuration changed elsewhere",
  conflictBody:
    "This draft was based on an older revision and was not saved. Load the latest Settings, then reapply and review your changes.",
  loadLatest: "Load latest Settings",
  lockTitle: "Another exclusive operation is active",
  lockBody:
    "Settings were not saved. Wait for the active operation to finish, then review and save again.",
  ioTitle: "Configuration could not be written",
  ioBody:
    "The backend reported a configuration I/O failure. The current draft remains available.",
  disconnectedTitle: "The local service could not be reached",
  disconnectedBody:
    "Nothing was automatically retried. Check the local service, then choose the action again.",
  unexpectedTitle: "Settings could not be completed",
  csrfRefreshFailed:
    "The security token could not be refreshed. Reload the application before saving.",
  unsavedTitle: "Leave with unsaved Settings?",
  unsavedBody:
    "Your Settings draft has not been saved. Leaving this route will discard it.",
  closeUnsaved: "Close and keep editing",
  stay: "Keep editing",
  leave: "Discard draft and leave",
} as const;

export const defaultPreviewSample = {
  file_extension: ".flac",
  metadata: {
    album: "Night Signals",
    album_artist: "North Harbor",
    artist: "North Harbor",
    disc_number: 1,
    disc_total: 1,
    title: "First Light",
    track_number: 1,
    track_total: 10,
    year: 2026,
  },
} satisfies Pick<PathPreviewRequest, "file_extension" | "metadata">;
