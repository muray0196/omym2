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

const CSRF_HEADER = "X-OMYM2-CSRF-Token";

export async function getSettings(): Promise<SettingsState> {
  return requestJson<SettingsState>("/api/settings");
}

export async function validateSettings(config: AppConfig): Promise<SettingsValidateResult> {
  return requestJson<SettingsValidateResult>("/api/settings/validate", {
    method: "POST",
    body: JSON.stringify({ config })
  });
}

export async function saveSettings(config: AppConfig, csrfToken: string): Promise<SettingsSaveResult> {
  return requestJson<SettingsSaveResult>("/api/settings/save", {
    method: "POST",
    headers: { [CSRF_HEADER]: csrfToken },
    body: JSON.stringify({ config })
  });
}

export async function getHistory(): Promise<HistoryResponse> {
  return requestJson<HistoryResponse>("/api/history");
}

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  return requestJson<RunDetailResponse>(`/api/history/${encodeURIComponent(runId)}`);
}

export async function getCheck(): Promise<CheckResponse> {
  return requestJson<CheckResponse>("/api/check");
}

export async function getTracks(): Promise<TracksResponse> {
  return requestJson<TracksResponse>("/api/tracks");
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    }
  });
  const payload = (await response.json()) as T;
  return payload;
}
