/*
Summary: Calls the local OMYM2 Web API from the Next console.
Why: Connects settings UI state to persisted TOML while preserving static previews.
*/

import {
  mockCheckResponse,
  mockHistoryResponse,
  mockRunDetailResponse,
  mockSaveSettings,
  mockSettingsState,
  mockTracksResponse,
  mockValidateSettings,
} from "./mock-data"
import type {
  AppConfig,
  CheckResponse,
  HistoryResponse,
  RunDetailResponse,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TracksResponse,
} from "./types"

const CSRF_HEADER = "X-OMYM2-CSRF-Token"
const MOCK_API_MODE = "mock"
const LOCAL_API_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"])

export async function getSettings(): Promise<SettingsState> {
  if (isMockApiMode()) {
    return clonePayload(mockSettingsState)
  }
  return requestJson<SettingsState>("/api/settings")
}

export async function getHistory(): Promise<HistoryResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockHistoryResponse)
  }
  return requestJson<HistoryResponse>("/api/history")
}

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockRunDetailResponse(runId))
  }
  return requestJson<RunDetailResponse>(`/api/history/${encodeURIComponent(runId)}`)
}

export async function getCheck(): Promise<CheckResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockCheckResponse)
  }
  return requestJson<CheckResponse>("/api/check")
}

export async function getTracks(): Promise<TracksResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockTracksResponse)
  }
  return requestJson<TracksResponse>("/api/tracks")
}

export async function validateSettings(config: AppConfig): Promise<SettingsValidateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockValidateSettings(config))
  }
  return requestJson<SettingsValidateResult>("/api/settings/validate", {
    body: JSON.stringify({ config }),
    method: "POST",
  })
}

export async function saveSettings(
  config: AppConfig,
  csrfToken: string,
): Promise<SettingsSaveResult> {
  if (isMockApiMode()) {
    return clonePayload(mockSaveSettings(config))
  }
  return requestJson<SettingsSaveResult>("/api/settings/save", {
    body: JSON.stringify({ config }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(url, { ...init, headers })
  const body = await response.text()
  if (body.trim() === "") {
    throw new Error(
      `OMYM2 Web API returned an empty response for ${url} (HTTP ${response.status}).`,
    )
  }
  if (!isJsonContentType(response.headers.get("content-type") ?? "")) {
    throw new Error(
      `OMYM2 Web API returned a non-JSON response for ${url} (HTTP ${response.status}).`,
    )
  }

  try {
    return JSON.parse(body) as T
  } catch {
    throw new Error(`OMYM2 Web API returned invalid JSON for ${url} (HTTP ${response.status}).`)
  }
}

function isMockApiMode(): boolean {
  if (process.env.NEXT_PUBLIC_OMYM2_API_MODE === MOCK_API_MODE) {
    return true
  }
  if (typeof window === "undefined") {
    return false
  }
  return !LOCAL_API_HOSTNAMES.has(window.location.hostname)
}

function isJsonContentType(contentType: string): boolean {
  const mediaType = contentType.split(";")[0]?.trim().toLowerCase() ?? ""
  return mediaType === "application/json" || mediaType.endsWith("+json")
}

function clonePayload<T>(payload: T): T {
  return structuredClone(payload)
}
