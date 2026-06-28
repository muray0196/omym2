/*
Summary: Calls the React-facing OMYM2 Web API.
Why: Centralizes local API errors and design-preview mock behavior.
*/

import type {
  AppConfig,
  CheckResponse,
  HistoryResponse,
  RunDetailResponse,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TracksResponse
} from "../types";
import {
  mockCheckResponse,
  mockHistoryResponse,
  mockRunDetailResponse,
  mockSaveSettings,
  mockSettingsState,
  mockTracksResponse,
  mockValidateSettings
} from "./mockData";

const CSRF_HEADER = "X-OMYM2-CSRF-Token";
const MOCK_API_MODE = "mock";

export async function getSettings(): Promise<SettingsState> {
  if (isMockApiMode()) {
    return clonePayload(mockSettingsState);
  }
  return requestJson<SettingsState>("/api/settings");
}

export async function validateSettings(config: AppConfig): Promise<SettingsValidateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockValidateSettings(config));
  }
  return requestJson<SettingsValidateResult>("/api/settings/validate", {
    method: "POST",
    body: JSON.stringify({ config })
  });
}

export async function saveSettings(config: AppConfig, csrfToken: string): Promise<SettingsSaveResult> {
  if (isMockApiMode()) {
    return clonePayload(mockSaveSettings(config));
  }
  return requestJson<SettingsSaveResult>("/api/settings/save", {
    method: "POST",
    headers: { [CSRF_HEADER]: csrfToken },
    body: JSON.stringify({ config })
  });
}

export async function getHistory(): Promise<HistoryResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockHistoryResponse);
  }
  return requestJson<HistoryResponse>("/api/history");
}

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockRunDetailResponse(runId));
  }
  return requestJson<RunDetailResponse>(`/api/history/${encodeURIComponent(runId)}`);
}

export async function getCheck(): Promise<CheckResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockCheckResponse);
  }
  return requestJson<CheckResponse>("/api/check");
}

export async function getTracks(): Promise<TracksResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockTracksResponse);
  }
  return requestJson<TracksResponse>("/api/tracks");
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, {
    ...init,
    headers
  });
  const body = await response.text();

  if (body.trim() === "") {
    throw new Error(
      `OMYM2 Web API returned an empty response for ${url} (HTTP ${response.status}). The OMYM2 Web API may not be running.`
    );
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!isJsonContentType(contentType)) {
    throw new Error(`OMYM2 Web API returned a non-JSON response for ${url} (HTTP ${response.status}).`);
  }

  try {
    return JSON.parse(body) as T;
  } catch {
    throw new Error(`OMYM2 Web API returned invalid JSON for ${url} (HTTP ${response.status}).`);
  }
}

function isMockApiMode(): boolean {
  return import.meta.env.VITE_OMYM2_API_MODE === MOCK_API_MODE;
}

function isJsonContentType(contentType: string): boolean {
  const mediaType = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return mediaType === "application/json" || mediaType.endsWith("+json");
}

function clonePayload<T>(payload: T): T {
  return structuredClone(payload);
}
