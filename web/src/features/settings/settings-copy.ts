/**
 * Summary: Centralizes English copy and sample values for the Settings workflow.
 * Why: Keeps recovery, review, conflict, and save language consistent across form states.
 */
import type { PathPreviewRequest } from "../../api/generated";

export const settingsCopy = {
  eyebrow: "Configuration",
  title: "Settings",
  description:
    "Edit paths, planning policy, integrations, and runtime controls. Save applies valid changes; Review changes previews the diff.",
  loading: "Loading Settings…",
  loadError: "Settings could not be loaded",
  retry: "Try again",
  recoveryTitle: "Configuration recovery",
  recoveryBody:
    "The saved configuration is invalid. Fix this draft and choose Save Settings; valid changes apply immediately.",
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
  artistDisplayNamesTitle: "Artist display names",
  artistDisplayNamesHelp:
    "Map exact source artist text to a full display name for path planning and preview. These names do not change embedded tags or compact artist IDs. With no entries, source names remain unchanged.",
  displayNameEntriesTitle: "Preferred full display names",
  noDisplayNameEntries: "No artist display-name preferences are in this draft.",
  displayName: "Display name",
  manualDisplayNameSource: "New display-name source artist",
  manualDisplayName: "New full display name",
  addDisplayName: "Add display name",
  artistIdsTitle: "Artist IDs",
  artistIdsHelp:
    "Generation changes only this draft. Save before generated entries become persistent.",
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
  musicbrainzTitle: "MusicBrainz",
  musicbrainzHelp:
    "Configure optional artist-name lookup. The application name and contact identify this installation to MusicBrainz; disabling lookup keeps naming local-only.",
  musicbrainzEnabled: "Enable MusicBrainz lookup",
  musicbrainzApplicationName: "Application name",
  musicbrainzContact: "Contact",
  musicbrainzTimeout: "Request timeout (seconds)",
  musicbrainzRetryLimit: "Retry limit",
  musicbrainzRateLimit: "Rate limit (seconds)",
  musicbrainzCachePolicy: "Accepted-result cache policy",
  fasttextTitle: "fastText",
  fasttextHelp:
    "Choose an optional language-identification model and the minimum confidence required to use its result.",
  fasttextModelPath: "Model path",
  fasttextModelPathHelp:
    "Leave empty to disable fastText language identification.",
  fasttextMinimumConfidence: "Minimum confidence",
  hashingTitle: "Hashing",
  hashingHelp:
    "Adjust how much file data is read at a time. This affects hashing performance, not content-hash identity.",
  hashingReadChunkSize: "Read chunk size (bytes)",
  loggingTitle: "Logging",
  loggingHelp:
    "Choose where application logs are written and how rotated log files are retained.",
  loggingDestination: "Relative log destination",
  loggingDestinationHelp:
    "Leave empty to use the application-data default destination.",
  loggingLevel: "Log level",
  loggingRotationMaxBytes: "Rotation size (bytes)",
  loggingRetentionFiles: "Retained files",
  loggingRestart:
    "Restart required: logging changes take effect the next time the application starts.",
  companionsTitle: "Companion assets",
  companionsHelp:
    "Control whether newly created plans may include associated lyrics and artwork files.",
  companionsEnabled: "Enable companion lyrics and artwork",
  unprocessedTitle: "Unprocessed files",
  unprocessedHelp:
    "Control reviewed collection of files that are not claimed by music or companion processing.",
  unprocessedEnabled: "Enable unprocessed-file collection",
  unprocessedDirectory: "Destination directory name",
  unprocessedDirectoryHelp:
    "Use one portable relative folder name. Separators, roots, dot references, trailing dots or spaces, and Windows reserved names are rejected.",
  unprocessedResultPreviewLimit: "Result preview limit",
  unprocessedResultPreviewLimitHelp:
    "Choose how many reviewed unprocessed results are shown at once. Allowed range:",
  previewTitle: "Path preview",
  previewBody:
    "Preview updates automatically from this draft and the sample metadata below without reading persisted state.",
  sampleArtist: "Sample artist",
  sampleAlbumArtist: "Sample album artist",
  sampleAlbum: "Sample album",
  sampleTitle: "Sample title",
  sampleYear: "Sample year",
  sampleDisc: "Sample disc number",
  sampleTrack: "Sample track number",
  sampleExtension: "Sample file extension",
  previewing: "Updating preview…",
  previewError:
    "Path preview could not be updated. The last available result is still shown.",
  retryPreview: "Retry preview",
  previewUnavailable: "No path could be rendered.",
  review: "Review changes",
  reviewing: "Reviewing changes…",
  reviewTitle: "Changes preview",
  reviewNeeded:
    "Review is optional. Save Settings validates and applies this draft in one action.",
  reviewOutdated:
    "The draft changed after this preview. Review again to refresh the changes shown here.",
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
  savedBody: "Your changes were validated and applied.",
  saveUnavailable:
    "Saving is unavailable in the current runtime state. Change review and path preview remain available.",
  conflictTitle: "Configuration changed elsewhere",
  conflictBody:
    "This draft was based on an older revision and was not saved. Load the latest Settings, then reapply your changes.",
  loadLatest: "Load latest Settings",
  lockTitle: "Another exclusive operation is active",
  lockBody:
    "Settings were not saved. Wait for the active operation to finish, then save again.",
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
  file_extension: ".FLAC",
  metadata: {
    album: "Example Album",
    album_artist: "Aimer",
    artist: "Aimer",
    disc_number: 1,
    disc_total: 2,
    title: "Example Song",
    track_number: 3,
    year: 2024,
  },
} satisfies Pick<PathPreviewRequest, "file_extension" | "metadata">;
