"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import {
  getCheck,
  getHistory,
  getRunDetail,
  getSettings,
  getTracks,
  generateArtistIds as generateArtistIdsRequest,
  saveSettings as saveSettingsRequest,
  validateSettings,
} from "./api-client"
import { savedArtistIdEntries } from "./lib"
import { defaultConfig, mockSettingsState } from "./mock-data"
import type {
  AppConfig,
  CheckIssue,
  PathPreview,
  RunDetail,
  RunSummary,
  SettingsChange,
  SettingsChoices,
  TrackSummary,
  ValidationResult,
} from "./types"

export type Route =
  | { name: "dashboard" }
  | { name: "settings" }
  | { name: "path-policy" }
  | { name: "runs" }
  | { name: "run-detail"; runId: string }
  | { name: "check" }
  | { name: "tracks" }

export type NavKey = "dashboard" | "settings" | "path-policy" | "runs" | "check" | "tracks"

interface AppContextValue {
  route: Route
  navigate: (route: Route) => void
  /** The currently persisted (saved) configuration. */
  savedConfig: AppConfig
  /** The in-progress draft being edited. */
  draftConfig: AppConfig
  setDraftConfig: (updater: (prev: AppConfig) => AppConfig) => void
  saveConfig: () => Promise<boolean>
  resetDraft: () => void
  generateArtistIds: (artistNames: string[], overwrite: boolean) => Promise<boolean>
  checkErrors: string[]
  checkIssues: CheckIssue[]
  checkLoaded: boolean
  historyErrors: string[]
  historyLoaded: boolean
  loadRunDetail: (runId: string) => Promise<void>
  runDetailErrors: Record<string, string[]>
  runDetailLoading: Record<string, boolean>
  runDetails: Record<string, RunDetail | null>
  runs: RunSummary[]
  settingsChoices: SettingsChoices
  settingsChanges: SettingsChange[]
  settingsErrors: string[]
  settingsLoadError: string | null
  settingsPreview: PathPreview
  settingsValidation: ValidationResult
  trackErrors: string[]
  tracks: TrackSummary[]
  tracksLoaded: boolean
  validateDraft: () => Promise<boolean>
}

const AppContext = createContext<AppContextValue | null>(null)

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp must be used within AppProvider")
  return ctx
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>({ name: "dashboard" })
  const [savedConfig, setSavedConfig] = useState<AppConfig>(defaultConfig)
  const [draftConfig, setDraftConfigState] = useState<AppConfig>(defaultConfig)
  const [settingsChoices, setSettingsChoices] = useState<SettingsChoices>(mockSettingsState.choices)
  const [settingsChanges, setSettingsChanges] = useState<SettingsChange[]>([])
  const [settingsErrors, setSettingsErrors] = useState<string[]>([])
  const [settingsLoadError, setSettingsLoadError] = useState<string | null>(null)
  const [settingsPreview, setSettingsPreview] = useState<PathPreview>(mockSettingsState.preview)
  const [settingsValidation, setSettingsValidation] = useState<ValidationResult>(
    mockSettingsState.validation,
  )
  const [csrfToken, setCsrfToken] = useState(mockSettingsState.csrf_token)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [historyErrors, setHistoryErrors] = useState<string[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [runDetails, setRunDetails] = useState<Record<string, RunDetail | null>>({})
  const [runDetailErrors, setRunDetailErrors] = useState<Record<string, string[]>>({})
  const [runDetailLoading, setRunDetailLoading] = useState<Record<string, boolean>>({})
  const [checkIssues, setCheckIssues] = useState<CheckIssue[]>([])
  const [checkErrors, setCheckErrors] = useState<string[]>([])
  const [checkLoaded, setCheckLoaded] = useState(false)
  const [tracks, setTracks] = useState<TrackSummary[]>([])
  const [trackErrors, setTrackErrors] = useState<string[]>([])
  const [tracksLoaded, setTracksLoaded] = useState(false)

  useEffect(() => {
    function syncRouteFromLocation() {
      setRoute(routeFromPath(window.location.pathname))
    }

    syncRouteFromLocation()
    window.addEventListener("popstate", syncRouteFromLocation)
    return () => window.removeEventListener("popstate", syncRouteFromLocation)
  }, [])

  useEffect(() => {
    let cancelled = false

    getSettings()
      .then((state) => {
        if (cancelled) return
        setSavedConfig(state.config)
        setDraftConfigState(state.config)
        setSettingsChoices(state.choices)
        setSettingsErrors(state.errors)
        setSettingsLoadError(null)
        setSettingsPreview(state.preview)
        setSettingsValidation(state.validation)
        setCsrfToken(state.csrf_token)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSettingsLoadError(error instanceof Error ? error.message : "Settings failed to load.")
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadInspectionState() {
      const [historyResult, checkResult, tracksResult] = await Promise.allSettled([
        getHistory(),
        getCheck(),
        getTracks(),
      ])
      if (cancelled) return

      if (historyResult.status === "fulfilled") {
        setRuns(historyResult.value.runs)
        setHistoryErrors(historyResult.value.errors)
      } else {
        setHistoryErrors([errorMessage(historyResult.reason, "Run history failed to load.")])
      }
      setHistoryLoaded(true)

      if (checkResult.status === "fulfilled") {
        setCheckIssues(checkResult.value.issues)
        setCheckErrors(checkResult.value.errors)
      } else {
        setCheckErrors([errorMessage(checkResult.reason, "Check issues failed to load.")])
      }
      setCheckLoaded(true)

      if (tracksResult.status === "fulfilled") {
        setTracks(tracksResult.value.tracks)
        setTrackErrors(tracksResult.value.errors)
      } else {
        setTrackErrors([errorMessage(tracksResult.reason, "Tracks failed to load.")])
      }
      setTracksLoaded(true)
    }

    void loadInspectionState()
    return () => {
      cancelled = true
    }
  }, [])

  const loadRunDetail = useCallback(async (runId: string) => {
    setRunDetailLoading((current) => ({ ...current, [runId]: true }))
    try {
      const result = await getRunDetail(runId)
      setRunDetails((current) => ({ ...current, [runId]: result.detail }))
      setRunDetailErrors((current) => ({ ...current, [runId]: result.errors }))
    } catch (error: unknown) {
      setRunDetails((current) => ({ ...current, [runId]: null }))
      setRunDetailErrors((current) => ({
        ...current,
        [runId]: [errorMessage(error, "Run detail failed to load.")],
      }))
    } finally {
      setRunDetailLoading((current) => ({ ...current, [runId]: false }))
    }
  }, [])

  // Apply theme to <html>.
  useEffect(() => {
    const root = document.documentElement
    const theme = draftConfig.ui.theme
    const apply = (dark: boolean) => {
      root.classList.toggle("dark", dark)
      root.classList.toggle("light", !dark)
      // OLED layers pure-black surfaces on top of the dark palette.
      root.classList.toggle("oled", theme === "oled")
    }
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)")
      apply(mq.matches)
      const onChange = (e: MediaQueryListEvent) => apply(e.matches)
      mq.addEventListener("change", onChange)
      return () => mq.removeEventListener("change", onChange)
    }
    apply(theme === "dark" || theme === "oled")
  }, [draftConfig.ui.theme])

  const value = useMemo<AppContextValue>(
    () => ({
      route,
      navigate: (next) => {
        setRoute(next)
        window.history.pushState({}, "", routeToPath(next))
        window.scrollTo({ top: 0 })
      },
      savedConfig,
      draftConfig,
      setDraftConfig: (updater) => {
        setDraftConfigState((prev) => updater(prev))
        setSettingsChanges([])
        setSettingsErrors([])
      },
      saveConfig: async () => {
        try {
          const result = await saveSettingsRequest(draftConfig, csrfToken)
          setSettingsChanges(result.changes)
          setSettingsErrors(result.errors)
          if (result.preview) {
            setSettingsPreview(result.preview)
          }
          if (result.validation) {
            setSettingsValidation(result.validation)
          }
          if (result.saved && result.config) {
            setSavedConfig(result.config)
            setDraftConfigState(result.config)
          }
          return result.saved
        } catch (error: unknown) {
          setSettingsErrors([error instanceof Error ? error.message : "Settings save failed."])
          return false
        }
      },
      resetDraft: () => {
        setDraftConfigState(savedConfig)
        setSettingsChanges([])
        setSettingsErrors([])
      },
      generateArtistIds: async (artistNames, overwrite) => {
        try {
          const result = await generateArtistIdsRequest(artistNames, overwrite, csrfToken)
          setSettingsErrors(result.errors)
          if (!result.generated) return false
          const generatedEntries = savedArtistIdEntries(result.entries)
          setSavedConfig((prev) => ({
            ...prev,
            artist_ids: {
              ...prev.artist_ids,
              entries: { ...prev.artist_ids.entries, ...generatedEntries },
            },
          }))
          setDraftConfigState((prev) => ({
            ...prev,
            artist_ids: {
              ...prev.artist_ids,
              entries: { ...prev.artist_ids.entries, ...generatedEntries },
            },
          }))
          setSettingsChanges([])
          return true
        } catch (error: unknown) {
          setSettingsErrors([
            error instanceof Error ? error.message : "Artist ID generation failed.",
          ])
          return false
        }
      },
      checkErrors,
      checkIssues,
      checkLoaded,
      historyErrors,
      historyLoaded,
      loadRunDetail,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      settingsChoices,
      settingsChanges,
      settingsErrors,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
      trackErrors,
      tracks,
      tracksLoaded,
      validateDraft: async () => {
        try {
          const result = await validateSettings(draftConfig)
          setSettingsChanges(result.changes)
          setSettingsErrors(result.errors)
          setSettingsPreview(result.preview)
          setSettingsValidation((current) => ({
            config_hash: current.config_hash,
            errors: result.errors,
            valid: result.valid,
          }))
          return result.valid
        } catch (error: unknown) {
          setSettingsErrors([
            error instanceof Error ? error.message : "Settings validation failed.",
          ])
          return false
        }
      },
    }),
    [
      checkErrors,
      checkIssues,
      checkLoaded,
      csrfToken,
      draftConfig,
      historyErrors,
      historyLoaded,
      loadRunDetail,
      route,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      savedConfig,
      settingsChanges,
      settingsChoices,
      settingsErrors,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
      trackErrors,
      tracks,
      tracksLoaded,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

function routeFromPath(pathname: string): Route {
  if (pathname === "/settings") return { name: "settings" }
  if (pathname === "/path-policy") return { name: "path-policy" }
  if (pathname === "/history") return { name: "runs" }
  if (pathname.startsWith("/history/")) {
    return { name: "run-detail", runId: decodeURIComponent(pathname.replace("/history/", "")) }
  }
  if (pathname === "/check") return { name: "check" }
  if (pathname === "/tracks") return { name: "tracks" }
  return { name: "dashboard" }
}

function routeToPath(route: Route): string {
  switch (route.name) {
    case "settings":
      return "/settings"
    case "path-policy":
      return "/path-policy"
    case "runs":
      return "/history"
    case "run-detail":
      return `/history/${encodeURIComponent(route.runId)}`
    case "check":
      return "/check"
    case "tracks":
      return "/tracks"
    case "dashboard":
    default:
      return "/"
  }
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}
