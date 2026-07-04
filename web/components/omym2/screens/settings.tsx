"use client"

import {
  Braces,
  Database,
  FileCheck2,
  FolderTree,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Tags,
  WandSparkles,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useApp } from "../app-context"
import { previewSettings } from "../api-client"
import { TEMPLATE_TOKENS, configHash, diffConfig, validateConfig } from "../lib"
import type { AppConfig } from "../types"
import { Button, Mono, Notice, Panel, StatusBadge } from "../primitives"
import { Field, Select, TextArea, TextInput, Toggle } from "../forms"
import { ChangeDiff, PathPreview } from "../widgets"
import { PageHeading } from "./page-heading"

const THEME_LABELS: Record<string, string> = {
  dark: "Dark",
  light: "Light",
  system: "System",
}

type SaveState = "idle" | "saving" | "success" | "error"

type SectionKey = "paths" | "behavior" | "path-policy" | "metadata" | "rules"

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: "paths", label: "Paths" },
  { key: "behavior", label: "Behavior" },
  { key: "path-policy", label: "Path policy" },
  { key: "metadata", label: "Metadata & IDs" },
  { key: "rules", label: "Rules & UI" },
]

export function SettingsScreen() {
  const {
    draftConfig,
    generateArtistIds,
    savedConfig,
    saveConfig,
    setDraftConfig,
    settingsChanges,
    settingsChoices,
    settingsErrors,
    settingsLoadError,
    settingsPreview,
    settingsValidation,
    validateDraft,
  } = useApp()
  const [saveState, setSaveState] = useState<SaveState>("idle")
  const [artistInput, setArtistInput] = useState("")
  const [artistOverwrite, setArtistOverwrite] = useState(false)
  const [artistGenerationState, setArtistGenerationState] = useState<SaveState>("idle")
  const [validated, setValidated] = useState(true)
  const [draftPreview, setDraftPreview] = useState(settingsPreview)
  const [section, setSection] = useState<SectionKey>("paths")

  const localValidation = useMemo(() => validateConfig(draftConfig), [draftConfig])
  const validation = validated
    ? settingsValidation
    : { config_hash: null, errors: localValidation.errors, valid: localValidation.valid }
  const diff = useMemo(() => {
    if (settingsChanges.length > 0) {
      return settingsChanges.map((change) => ({
        after: change.after,
        before: change.before,
        field: change.label,
      }))
    }
    return diffConfig(savedConfig, draftConfig)
  }, [draftConfig, savedConfig, settingsChanges])
  const hash = useMemo(() => configHash(draftConfig), [draftConfig])
  const preview = validated ? settingsPreview : draftPreview
  const validationErrors = uniqueMessages([...settingsErrors, ...validation.errors])

  useEffect(() => {
    setDraftPreview(settingsPreview)
  }, [settingsPreview])

  useEffect(() => {
    if (validated) return

    let cancelled = false
    const timeout = window.setTimeout(() => {
      previewSettings(draftConfig)
        .then((result) => {
          if (!cancelled) setDraftPreview(result)
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setDraftPreview({
              path: null,
              errors: [error instanceof Error ? error.message : "Path preview failed."],
            })
          }
        })
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [draftConfig, validated])

  // Generic nested updater.
  function update<K extends keyof AppConfig>(key: K, value: Partial<AppConfig[K]>) {
    setDraftConfig((prev) => ({ ...prev, [key]: { ...(prev[key] as object), ...value } }))
    setSaveState("idle")
    setValidated(false)
  }

  function appendToken(token: string) {
    update("path_policy", {
      template: draftConfig.path_policy.template + token,
    })
  }

  function updateArtistIds(value: Partial<AppConfig["artist_ids"]>) {
    update("artist_ids", value)
  }

  function updateArtistIdEntry(sourceArtist: string, artistId: string) {
    updateArtistIds({
      entries: {
        ...draftConfig.artist_ids.entries,
        [sourceArtist]: artistId,
      },
    })
  }

  async function handleGenerateArtistIds() {
    const artistNames = artistInput
      .split(/\r?\n|,/)
      .map((name) => name.trim())
      .filter(Boolean)
    if (artistNames.length === 0) return
    setArtistGenerationState("saving")
    const generated = await generateArtistIds(artistNames, artistOverwrite)
    setArtistGenerationState(generated ? "success" : "error")
    if (generated) {
      setArtistInput("")
      setValidated(false)
    }
  }

  async function handleValidate() {
    setSaveState("idle")
    await validateDraft()
    setValidated(true)
  }

  async function handleSave() {
    if (!validation.valid) return
    setSaveState("saving")
    const saved = await saveConfig()
    setValidated(saved)
    setSaveState(saved ? "success" : "error")
  }

  const pp = draftConfig.path_policy
  const artistEntries = Object.entries(draftConfig.artist_ids.entries).sort(([a], [b]) =>
    a.localeCompare(b),
  )
  const modeOptions = toOptions(settingsChoices.command_modes, {
    plan_first: "plan_first (review first)",
  })
  const targetExistsOptions = toOptions(settingsChoices.target_exists_policies)
  const duplicateHashOptions = toOptions(settingsChoices.duplicate_hash_policies)
  const missingMetadataOptions = toOptions(settingsChoices.missing_metadata_policies)
  const themeOptions = toOptions(settingsChoices.ui_themes, THEME_LABELS)

  return (
    <>
      <PageHeading
        title="Settings"
        description="Configure OMYM2 and review every change before saving. Validation and preview run locally; the CLI performs the actual work."
      />
      {settingsLoadError ? (
        <Notice tone="danger" title="Settings load failed" className="mb-6">
          {settingsLoadError}
        </Notice>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* Left: grouped editor with section tabs */}
        <div className="flex min-w-0 flex-col gap-6">
          <nav
            aria-label="Settings sections"
            className="sticky top-0 z-10 -mx-1 flex gap-1 overflow-x-auto rounded-lg border border-border bg-card p-1"
          >
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setSection(s.key)}
                aria-current={section === s.key ? "true" : undefined}
                className={
                  section === s.key
                    ? "whitespace-nowrap rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground"
                    : "whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                }
              >
                {s.label}
              </button>
            ))}
          </nav>

          {section === "paths" ? (
            <Panel
              title="Paths"
              icon={Database}
              description="Local filesystem paths used by OMYM2."
            >
              <div className="flex flex-col gap-4">
                <Field
                  label="Library path"
                  help="Absolute path to the managed music library root. Canonical paths resolve under this directory."
                >
                  {(id) => (
                    <TextInput
                      id={id}
                      mono
                      placeholder="/music/library"
                      value={draftConfig.paths.library ?? ""}
                      onChange={(e) => update("paths", { library: e.target.value || null })}
                    />
                  )}
                </Field>
                <Field
                  label="Incoming path"
                  help="Absolute path to the folder scanned for new files to import."
                >
                  {(id) => (
                    <TextInput
                      id={id}
                      mono
                      placeholder="/music/incoming"
                      value={draftConfig.paths.incoming ?? ""}
                      onChange={(e) => update("paths", { incoming: e.target.value || null })}
                    />
                  )}
                </Field>
              </div>
            </Panel>
          ) : null}

          {section === "behavior" ? (
            <>
              <Panel title="Add behavior" icon={Plus} description="Defaults for `omym2 add`.">
                <div className="flex flex-col gap-4">
                  <Field
                    label="Default mode"
                    help="Plan-first behavior is safer: it builds a reviewable Plan before any files move."
                  >
                    {(id) => (
                      <Select
                        id={id}
                        options={modeOptions}
                        value={draftConfig.add.default_mode}
                        onChange={(e) => update("add", { default_mode: e.target.value })}
                      />
                    )}
                  </Field>
                  <Toggle
                    checked={draftConfig.add.auto_apply}
                    onChange={(v) => update("add", { auto_apply: v })}
                    label="Auto-apply"
                    help="When enabled, plans are applied without a manual review step. Leave off for safety."
                  />
                </div>
              </Panel>

              <Panel
                title="Organize behavior"
                icon={FolderTree}
                description="Defaults for `omym2 organize`."
              >
                <div className="flex flex-col gap-4">
                  <Field label="Default mode">
                    {(id) => (
                      <Select
                        id={id}
                        options={modeOptions}
                        value={draftConfig.organize.default_mode}
                        onChange={(e) => update("organize", { default_mode: e.target.value })}
                      />
                    )}
                  </Field>
                  <Toggle
                    checked={draftConfig.organize.auto_apply}
                    onChange={(v) => update("organize", { auto_apply: v })}
                    label="Auto-apply"
                  />
                  <Toggle
                    checked={draftConfig.organize.only_misplaced}
                    onChange={(v) => update("organize", { only_misplaced: v })}
                    label="Only misplaced"
                    help="Restrict organize to files whose current path differs from the canonical path."
                  />
                </div>
              </Panel>

              <Panel
                title="Refresh behavior"
                icon={RotateCcw}
                description="Defaults for `omym2 refresh`."
              >
                <div className="flex flex-col gap-4">
                  <Field label="Default mode">
                    {(id) => (
                      <Select
                        id={id}
                        options={modeOptions}
                        value={draftConfig.refresh.default_mode}
                        onChange={(e) => update("refresh", { default_mode: e.target.value })}
                      />
                    )}
                  </Field>
                  <Toggle
                    checked={draftConfig.refresh.auto_apply}
                    onChange={(v) => update("refresh", { auto_apply: v })}
                    label="Auto-apply"
                  />
                </div>
              </Panel>
            </>
          ) : null}

          {section === "path-policy" ? (
            <Panel
              title="Path policy"
              icon={Braces}
              description="How canonical relative paths are generated."
            >
              <div className="flex flex-col gap-4">
                <Field
                  label="Template"
                  help="Templates must NOT include a file extension. The source file extension is appended automatically after rendering."
                >
                  {(id) => (
                    <TextArea
                      id={id}
                      mono
                      rows={2}
                      value={pp.template}
                      onChange={(e) => update("path_policy", { template: e.target.value })}
                    />
                  )}
                </Field>
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                    Allowed tokens (click to insert)
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {TEMPLATE_TOKENS.map((token) => (
                      <button
                        key={token}
                        type="button"
                        onClick={() => appendToken(token)}
                        className="rounded-md border border-border bg-muted px-2 py-1 font-mono text-xs text-foreground transition-colors hover:border-primary hover:bg-accent"
                      >
                        {token}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Unknown artist fallback">
                    {(id) => (
                      <TextInput
                        id={id}
                        value={pp.unknown_artist}
                        onChange={(e) => update("path_policy", { unknown_artist: e.target.value })}
                      />
                    )}
                  </Field>
                  <Field label="Unknown album fallback">
                    {(id) => (
                      <TextInput
                        id={id}
                        value={pp.unknown_album}
                        onChange={(e) => update("path_policy", { unknown_album: e.target.value })}
                      />
                    )}
                  </Field>
                  <Field
                    label="Max filename length"
                    help="Applies to the final filename incl. extension."
                  >
                    {(id) => (
                      <TextInput
                        id={id}
                        type="number"
                        min={16}
                        value={pp.max_filename_length}
                        onChange={(e) =>
                          update("path_policy", {
                            max_filename_length: Number(e.target.value) || 0,
                          })
                        }
                      />
                    )}
                  </Field>
                </div>
                <Toggle
                  checked={pp.sanitize}
                  onChange={(v) => update("path_policy", { sanitize: v })}
                  label="Sanitize segments"
                  help="Replace filesystem-unsafe characters in each path segment."
                />
              </div>
            </Panel>
          ) : null}

          {section === "metadata" ? (
            <>
              <Panel title="Metadata rules" icon={Tags}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Toggle
                    checked={draftConfig.metadata.prefer_album_artist}
                    onChange={(v) => update("metadata", { prefer_album_artist: v })}
                    label="Prefer album artist"
                  />
                  <Toggle
                    checked={draftConfig.metadata.require_title}
                    onChange={(v) => update("metadata", { require_title: v })}
                    label="Require title"
                  />
                  <Toggle
                    checked={draftConfig.metadata.require_artist}
                    onChange={(v) => update("metadata", { require_artist: v })}
                    label="Require artist"
                  />
                  <Toggle
                    checked={draftConfig.metadata.require_album}
                    onChange={(v) => update("metadata", { require_album: v })}
                    label="Require album"
                  />
                </div>
              </Panel>

              <Panel
                title="Artist IDs"
                icon={WandSparkles}
                description="Editable values for the {artist_id} path token."
              >
                <div className="flex flex-col gap-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Max ID length">
                      {(id) => (
                        <TextInput
                          id={id}
                          type="number"
                          min={1}
                          value={draftConfig.artist_ids.max_length}
                          onChange={(e) =>
                            updateArtistIds({ max_length: Number(e.target.value) || 0 })
                          }
                        />
                      )}
                    </Field>
                    <Field label="Fallback ID">
                      {(id) => (
                        <TextInput
                          id={id}
                          mono
                          value={draftConfig.artist_ids.fallback_id}
                          onChange={(e) => updateArtistIds({ fallback_id: e.target.value })}
                        />
                      )}
                    </Field>
                  </div>
                  <Field
                    label="Generate from artists"
                    help="Separate names with commas or new lines."
                  >
                    {(id) => (
                      <TextArea
                        id={id}
                        rows={3}
                        value={artistInput}
                        onChange={(e) => setArtistInput(e.target.value)}
                        placeholder={"Aimer\nJohn Smith"}
                      />
                    )}
                  </Field>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <Toggle
                      checked={artistOverwrite}
                      onChange={setArtistOverwrite}
                      label="Overwrite existing"
                    />
                    <Button
                      variant="outline"
                      onClick={handleGenerateArtistIds}
                      disabled={artistGenerationState === "saving" || artistInput.trim() === ""}
                      className="sm:w-44"
                    >
                      <WandSparkles className="size-4" aria-hidden="true" />
                      {artistGenerationState === "saving" ? "Generating…" : "Generate"}
                    </Button>
                  </div>
                  {artistGenerationState === "success" ? (
                    <Notice tone="success" title="Artist IDs generated">
                      Saved generated entries to local config.
                    </Notice>
                  ) : null}
                  {artistGenerationState === "error" ? (
                    <Notice tone="danger" title="Artist ID generation failed">
                      {settingsErrors.join(" ") || "The local API rejected the request."}
                    </Notice>
                  ) : null}
                  <div className="overflow-hidden rounded-md border border-border">
                    <div className="grid grid-cols-[minmax(0,1fr)_minmax(7rem,11rem)] gap-2 border-b border-border bg-muted px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      <span>Artist</span>
                      <span>ID</span>
                    </div>
                    {artistEntries.length > 0 ? (
                      <div className="divide-y divide-border">
                        {artistEntries.map(([sourceArtist, artistId]) => (
                          <div
                            key={sourceArtist}
                            className="grid grid-cols-[minmax(0,1fr)_minmax(7rem,11rem)] gap-2 px-3 py-2"
                          >
                            <Mono className="truncate text-foreground" title={sourceArtist}>
                              {sourceArtist}
                            </Mono>
                            <TextInput
                              mono
                              value={artistId}
                              onChange={(e) => updateArtistIdEntry(sourceArtist, e.target.value)}
                              aria-label={`Artist ID for ${sourceArtist}`}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="px-3 py-4 text-sm text-muted-foreground">
                        No artist IDs saved.
                      </div>
                    )}
                  </div>
                </div>
              </Panel>
            </>
          ) : null}

          {section === "rules" ? (
            <>
              <Panel
                title="Collision rules"
                icon={FileCheck2}
                description="How conflicts are resolved during apply."
              >
                <div className="flex flex-col gap-4">
                  <Field label="On target exists">
                    {(id) => (
                      <Select
                        id={id}
                        options={targetExistsOptions}
                        value={draftConfig.collision.on_target_exists}
                        onChange={(e) =>
                          update("collision", { on_target_exists: e.target.value as never })
                        }
                      />
                    )}
                  </Field>
                  <Field label="On duplicate hash">
                    {(id) => (
                      <Select
                        id={id}
                        options={duplicateHashOptions}
                        value={draftConfig.collision.on_duplicate_hash}
                        onChange={(e) =>
                          update("collision", { on_duplicate_hash: e.target.value as never })
                        }
                      />
                    )}
                  </Field>
                  <Field label="On missing metadata">
                    {(id) => (
                      <Select
                        id={id}
                        options={missingMetadataOptions}
                        value={draftConfig.collision.on_missing_metadata}
                        onChange={(e) =>
                          update("collision", { on_missing_metadata: e.target.value as never })
                        }
                      />
                    )}
                  </Field>
                </div>
              </Panel>

              <Panel title="UI" icon={SlidersHorizontal}>
                <div className="flex flex-col gap-4">
                  <Field label="Theme">
                    {(id) => (
                      <Select
                        id={id}
                        options={themeOptions}
                        value={draftConfig.ui.theme}
                        onChange={(e) => update("ui", { theme: e.target.value as never })}
                      />
                    )}
                  </Field>
                  <Toggle
                    checked={draftConfig.ui.show_advanced_settings}
                    onChange={(v) => update("ui", { show_advanced_settings: v })}
                    label="Show advanced settings"
                  />
                </div>
              </Panel>
            </>
          ) : null}
        </div>

        {/* Right: sticky review sidebar */}
        <div className="flex flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
          <Panel title="Validation" icon={ShieldCheck}>
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <StatusBadge
                  status={validation.valid ? "valid" : "invalid"}
                  label={validation.valid ? "Valid" : "Invalid"}
                />
                {validated ? <span className="text-xs text-success">Validated</span> : null}
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Config hash</p>
                <Mono className="break-all text-xs text-foreground">
                  {validation.config_hash ?? hash}
                </Mono>
              </div>
              {validationErrors.length > 0 ? (
                <Notice tone="danger" title="Validation errors">
                  <ul className="list-inside list-disc space-y-0.5">
                    {validationErrors.map((err) => (
                      <li key={err}>{err}</li>
                    ))}
                  </ul>
                </Notice>
              ) : (
                <Notice tone="success">All configuration checks passed.</Notice>
              )}
            </div>
          </Panel>

          <Panel
            title="Path preview"
            icon={Braces}
            description="Sample output for the current template."
          >
            <PathPreview
              path={preview.path}
              errors={preview.errors}
              libraryRoot={draftConfig.paths.library}
            />
          </Panel>

          <Panel title="Changes">
            <ChangeDiff rows={diff} />
          </Panel>

          <Panel title="Save">
            <div className="flex flex-col gap-3">
              {saveState === "success" ? (
                <Notice tone="success" title="Settings saved">
                  Your configuration was persisted locally.
                </Notice>
              ) : null}
              {saveState === "error" ? (
                <Notice tone="danger" title="Save failed (HTTP 403)">
                  CSRF token rejected by the local API. Reload the console and try again.
                </Notice>
              ) : null}
              <Button variant="outline" onClick={handleValidate} className="w-full">
                <ShieldCheck className="size-4" aria-hidden="true" /> Validate
              </Button>
              <Button
                variant="default"
                onClick={handleSave}
                disabled={!validation.valid || diff.length === 0 || saveState === "saving"}
                className="w-full"
              >
                <Save className="size-4" aria-hidden="true" />
                {saveState === "saving" ? "Saving…" : "Save settings"}
              </Button>
              {!validation.valid ? (
                <p className="text-center text-xs text-muted-foreground">
                  Resolve validation errors before saving.
                </p>
              ) : diff.length === 0 ? (
                <p className="text-center text-xs text-muted-foreground">
                  No pending changes to save.
                </p>
              ) : null}
            </div>
          </Panel>
        </div>
      </div>
    </>
  )
}

function toOptions(values: string[], labels: Record<string, string> = {}) {
  return values.map((value) => ({ label: labels[value] ?? value, value }))
}

function uniqueMessages(messages: string[]): string[] {
  return Array.from(new Set(messages))
}
