/**
 * Summary: Wraps generated Settings SDK calls with typed data and failure handling.
 * Why: Keeps Config drafts on the generated boundary while distinguishing API and transport states.
 */
import {
  generateArtistIdDraft,
  getSettings,
  previewSettingsPath,
  saveSettings,
  validateSettings,
  type ApiFailureEnvelope,
  type ArtistIdDraftData,
  type ArtistIdDraftRequest,
  type PathPreview,
  type PathPreviewRequest,
  type SettingsCandidateData,
  type SettingsCandidateRequest,
  type SettingsData,
} from "../../api/generated";

export const settingsQueryKey = ["settings"] as const;

export class SettingsApiError extends Error {
  readonly envelope: ApiFailureEnvelope;
  readonly status: number;

  constructor(surface: string, envelope: ApiFailureEnvelope, status: number) {
    super(`${surface} returned a typed API failure.`);
    this.name = "SettingsApiError";
    this.envelope = envelope;
    this.status = status;
  }
}

export class SettingsTransportError extends Error {
  constructor(surface: string) {
    super(`${surface} could not reach the local service.`);
    this.name = "SettingsTransportError";
  }
}

export class SettingsUnexpectedDataError extends Error {
  constructor(surface: string) {
    super(`${surface} returned no readable data.`);
    this.name = "SettingsUnexpectedDataError";
  }
}

export async function readSettings(): Promise<SettingsData> {
  const response = await getSettings({ baseUrl: globalThis.location.origin });
  if (response.error !== undefined) {
    throwSettingsResponseError("Settings", response.error, response.response);
  }
  if (response.data.data === null) {
    throw new SettingsUnexpectedDataError("Settings");
  }
  return response.data.data;
}

export async function validateSettingsDraft(
  request: SettingsCandidateRequest,
): Promise<SettingsCandidateData> {
  const response = await validateSettings({
    baseUrl: globalThis.location.origin,
    body: request,
  });
  if (response.error !== undefined) {
    throwSettingsResponseError(
      "Settings validation",
      response.error,
      response.response,
    );
  }
  if (response.data.data === null) {
    throw new SettingsUnexpectedDataError("Settings validation");
  }
  return response.data.data;
}

export async function previewSettingsDraft(
  request: PathPreviewRequest,
): Promise<PathPreview> {
  const response = await previewSettingsPath({
    baseUrl: globalThis.location.origin,
    body: request,
  });
  if (response.error !== undefined) {
    throwSettingsResponseError(
      "Settings preview",
      response.error,
      response.response,
    );
  }
  if (response.data.data === null) {
    throw new SettingsUnexpectedDataError("Settings preview");
  }
  return response.data.data;
}

export async function generateArtistIds(
  request: ArtistIdDraftRequest,
): Promise<ArtistIdDraftData> {
  const response = await generateArtistIdDraft({
    baseUrl: globalThis.location.origin,
    body: request,
  });
  if (response.error !== undefined) {
    throwSettingsResponseError(
      "Artist ID generation",
      response.error,
      response.response,
    );
  }
  if (response.data.data === null) {
    throw new SettingsUnexpectedDataError("Artist ID generation");
  }
  return response.data.data;
}

export async function saveSettingsDraft(
  request: SettingsCandidateRequest,
  csrfToken: string,
): Promise<SettingsCandidateData> {
  const response = await saveSettings({
    baseUrl: globalThis.location.origin,
    body: request,
    headers: { "X-OMYM2-CSRF-Token": csrfToken },
  });
  if (response.error !== undefined) {
    throwSettingsResponseError(
      "Settings save",
      response.error,
      response.response,
    );
  }
  if (response.data.data === null) {
    throw new SettingsUnexpectedDataError("Settings save");
  }
  return response.data.data;
}

export function hasSettingsErrorCode(error: unknown, code: string): boolean {
  return (
    error instanceof SettingsApiError &&
    error.envelope.errors.some((diagnostic) => diagnostic.code === code)
  );
}

export function isCsrfInvalidSettingsError(error: unknown): boolean {
  return (
    error instanceof SettingsApiError &&
    error.status === 403 &&
    hasSettingsErrorCode(error, "csrf_invalid")
  );
}

function throwSettingsResponseError(
  surface: string,
  envelope: ApiFailureEnvelope,
  response: Response | undefined,
): never {
  if (response === undefined) {
    throw new SettingsTransportError(surface);
  }
  throw new SettingsApiError(surface, envelope, response.status);
}
