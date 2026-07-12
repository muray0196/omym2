"use client"

import { ArrowLeft, Braces, Music, RotateCcw } from "lucide-react"
import { useEffect, useState } from "react"
import { useApp } from "../app-context"
import { getTracksPage, previewSettings } from "../api-client"
import { TEMPLATE_TOKENS } from "../lib"
import type { PathPreview as PathPreviewResult, SampleMetadata, TrackSummary } from "../types"
import { Button, Mono, Notice, Panel } from "../primitives"
import { PillTab } from "../command-kit"
import { Field, TextArea, TextInput } from "../forms"
import { PathPreview } from "../widgets"
import { PageHeading } from "./page-heading"

interface SamplePreset {
  id: string
  label: string
  meta: SampleMetadata
}

const SAMPLE_PRESETS: SamplePreset[] = [
  {
    id: "complete",
    label: "Complete metadata (FLAC)",
    meta: {
      title: "Open the Door",
      artist: "Aimer",
      album: "Open α Door",
      album_artist: "Aimer",
      year: "2024",
      disc_number: "1",
      disc_total: "2",
      track_number: "3",
      extension: "flac",
    },
  },
  {
    id: "compilation",
    label: "Compilation (various artists)",
    meta: {
      title: "Anima",
      artist: "M2U",
      album: "Deemo",
      album_artist: "Various Artists",
      year: "2013",
      disc_number: "2",
      disc_total: "2",
      track_number: "5",
      extension: "mp3",
    },
  },
  {
    id: "missing",
    label: "Missing artist & album",
    meta: {
      title: "Untitled Demo",
      artist: "",
      album: "",
      album_artist: "",
      year: "",
      disc_number: "",
      disc_total: "",
      track_number: "1",
      extension: "m4a",
    },
  },
  {
    id: "unsafe",
    label: "Filesystem-unsafe characters",
    meta: {
      title: 'AC/DC: Live? "Best" <Mix>',
      artist: "AC/DC",
      album: "Who Made Who?",
      album_artist: "AC/DC",
      year: "1986",
      disc_number: "1",
      disc_total: "1",
      track_number: "2",
      extension: "flac",
    },
  },
]

const FIELD_LABELS: { key: keyof SampleMetadata; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "artist", label: "Artist" },
  { key: "album", label: "Album" },
  { key: "album_artist", label: "Album artist" },
  { key: "year", label: "Year" },
  { key: "disc_number", label: "Disc no." },
  { key: "disc_total", label: "Disc total" },
  { key: "track_number", label: "Track no." },
  { key: "extension", label: "Extension" },
]

function extensionFromCurrentPath(path: string): string {
  const filename = path.split("/").pop() ?? ""
  const separatorIndex = filename.lastIndexOf(".")
  if (separatorIndex <= 0 || separatorIndex === filename.length - 1) return ""
  return filename.slice(separatorIndex + 1)
}

function sampleMetadataFromTrack(track: TrackSummary): SampleMetadata {
  const metadata = track.metadata
  return {
    title: metadata.title ?? "",
    artist: metadata.artist ?? "",
    album: metadata.album ?? "",
    album_artist: metadata.album_artist ?? "",
    year: metadata.year === null ? "" : String(metadata.year),
    disc_number: metadata.disc_number === null ? "" : String(metadata.disc_number),
    disc_total: metadata.disc_total === null ? "" : String(metadata.disc_total),
    track_number: metadata.track_number === null ? "" : String(metadata.track_number),
    extension: extensionFromCurrentPath(track.current_path),
  }
}

export function PathPolicyScreen() {
  const { navigate, route, savedConfig } = useApp()
  const policy = savedConfig.path_policy
  const selectedTrackId = route.name === "path-policy" ? (route.trackId ?? null) : null

  const [presetId, setPresetId] = useState(SAMPLE_PRESETS[0].id)
  const [meta, setMeta] = useState<SampleMetadata>(SAMPLE_PRESETS[0].meta)
  const [preview, setPreview] = useState<PathPreviewResult>({ path: null, errors: [] })
  const [workingTemplate, setWorkingTemplate] = useState(policy.template)
  const [selectedTrack, setSelectedTrack] = useState<TrackSummary | null>(null)
  const [selectedTrackErrors, setSelectedTrackErrors] = useState<string[]>([])
  const [selectedTrackLoading, setSelectedTrackLoading] = useState(false)
  const templateModified = workingTemplate !== policy.template

  // Follow the saved template when it changes and no local edit is active.
  useEffect(() => {
    setWorkingTemplate(policy.template)
  }, [policy.template])

  useEffect(() => {
    if (selectedTrackId === null) {
      setSelectedTrack(null)
      setSelectedTrackErrors([])
      setSelectedTrackLoading(false)
      return
    }

    let cancelled = false
    setSelectedTrack(null)
    setSelectedTrackErrors([])
    setSelectedTrackLoading(true)
    getTracksPage({ trackId: selectedTrackId, limit: 1 })
      .then((response) => {
        if (cancelled) return
        const track = response.items[0] ?? null
        setSelectedTrack(track)
        setSelectedTrackErrors(
          track ? response.errors : ["Selected Track was not found.", ...response.errors],
        )
        if (track) {
          setMeta(sampleMetadataFromTrack(track))
          setPresetId("track")
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSelectedTrack(null)
        setSelectedTrackErrors([
          error instanceof Error ? error.message : "Selected Track failed to load.",
        ])
      })
      .finally(() => {
        if (!cancelled) setSelectedTrackLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedTrackId])

  useEffect(() => {
    if (selectedTrackId !== null || presetId !== "track") return
    setMeta(SAMPLE_PRESETS[0].meta)
    setPresetId(SAMPLE_PRESETS[0].id)
  }, [presetId, selectedTrackId])

  function clearSelectedTrackContext() {
    if (selectedTrackId !== null) {
      navigate({ name: "path-policy" }, { replace: true })
    }
  }

  function selectPreset(id: string) {
    clearSelectedTrackContext()
    setPresetId(id)
    const preset = SAMPLE_PRESETS.find((p) => p.id === id)
    if (preset) setMeta(preset.meta)
  }

  function updateMeta(key: keyof SampleMetadata, value: string) {
    clearSelectedTrackContext()
    setMeta((prev) => ({ ...prev, [key]: value }))
    setPresetId("custom")
  }

  function appendWorkingToken(token: string) {
    setWorkingTemplate((prev) => prev + token)
  }

  useEffect(() => {
    let cancelled = false
    const previewConfig = {
      ...savedConfig,
      path_policy: { ...savedConfig.path_policy, template: workingTemplate },
    }
    const timeout = window.setTimeout(() => {
      previewSettings(previewConfig, meta)
        .then((result) => {
          if (!cancelled) setPreview(result)
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setPreview({
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
  }, [savedConfig, meta, workingTemplate])

  return (
    <>
      <PageHeading
        title="Path policy preview"
        description="See how the saved path policy turns track metadata into a canonical relative path. The template and fallbacks are configured in Settings; this screen previews them against sample metadata."
        actions={
          selectedTrackId !== null ? (
            <Button
              variant="outline"
              onClick={() => navigate({ name: "tracks", trackId: selectedTrackId })}
            >
              <ArrowLeft className="size-4" aria-hidden="true" /> Return to Track
            </Button>
          ) : undefined
        }
      />

      {selectedTrackId !== null ? (
        <div className="mb-6 flex flex-col gap-3">
          {selectedTrackLoading ? (
            <Notice tone="info" title="Loading selected Track">
              Loading metadata for the current-policy diagnostic.
            </Notice>
          ) : null}
          {selectedTrack ? (
            <Notice tone="info" title="Current-policy diagnostic">
              <p>
                This preview uses the selected Track&apos;s persisted metadata and current path
                extension with the current working policy. It does not use, alter, or replace a
                recorded Plan target.
              </p>
              <Mono className="mt-1 block break-all text-ink" title={selectedTrack.current_path}>
                {selectedTrack.current_path}
              </Mono>
            </Notice>
          ) : null}
          {selectedTrackErrors.length > 0 ? (
            <Notice tone="warning" title="Track diagnostic is incomplete">
              {selectedTrackErrors.join(" ")}
            </Notice>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <Panel
            title="Active policy"
            icon={Braces}
            description="Read-only. Edit these values in Settings."
          >
            <dl className="flex flex-col gap-3 text-sm">
              <div className="border-b border-hairline pb-3">
                <dt className="text-xs uppercase tracking-wide text-mute">Template</dt>
                <dd className="mt-1">
                  <Mono className="break-all text-ink">{policy.template}</Mono>
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Unknown artist</dt>
                  <dd className="mt-0.5 font-medium text-ink">{policy.unknown_artist}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Unknown album</dt>
                  <dd className="mt-0.5 font-medium text-ink">{policy.unknown_album}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Max filename length</dt>
                  <dd className="mt-0.5 font-medium tabular-nums text-ink">
                    {policy.max_filename_length}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Disc style</dt>
                  <dd className="mt-0.5 font-medium text-ink">{policy.disc_number_style}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Disc condition</dt>
                  <dd className="mt-0.5 font-medium text-ink">{policy.disc_number_condition}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-mute">Sanitize segments</dt>
                  <dd className="mt-0.5 font-medium text-ink">
                    {policy.sanitize ? "Enabled" : "Disabled"}
                  </dd>
                </div>
              </div>
            </dl>
          </Panel>

          <Panel
            title="Sample metadata"
            icon={Music}
            description="Edit fields or pick a preset to test edge cases."
            actions={
              <Button variant="ghost" size="sm" onClick={() => selectPreset(SAMPLE_PRESETS[0].id)}>
                <RotateCcw className="size-3.5" aria-hidden="true" />
                Reset
              </Button>
            }
          >
            <div className="flex flex-col gap-4">
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mute">
                  Preset
                </p>
                <div
                  role="group"
                  aria-label="Sample metadata presets"
                  className="flex flex-wrap gap-1.5"
                >
                  {SAMPLE_PRESETS.map((preset) => (
                    <PillTab
                      key={preset.id}
                      active={presetId === preset.id}
                      onClick={() => selectPreset(preset.id)}
                    >
                      {preset.label}
                    </PillTab>
                  ))}
                  {presetId === "track" ? <PillTab active>Selected Track</PillTab> : null}
                  {presetId === "custom" ? <PillTab active>Custom (edited)</PillTab> : null}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {FIELD_LABELS.map(({ key, label }) => (
                  <Field key={key} label={label}>
                    {(id) => (
                      <TextInput
                        id={id}
                        mono
                        value={meta[key]}
                        onChange={(e) => updateMeta(key, e.target.value)}
                      />
                    )}
                  </Field>
                ))}
              </div>
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-6 lg:sticky lg:top-6 lg:self-start">
          <Panel
            title="Template"
            icon={Braces}
            description="Tweak the template here to preview without saving. Save in Settings to persist."
            actions={
              templateModified ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setWorkingTemplate(policy.template)}
                >
                  <RotateCcw className="size-3.5" aria-hidden="true" />
                  Revert to saved
                </Button>
              ) : null
            }
          >
            <div className="flex flex-col gap-4">
              <Field
                label="Working template"
                help="Templates must not include a file extension; the source extension is appended automatically."
              >
                {(id) => (
                  <TextArea
                    id={id}
                    mono
                    rows={2}
                    value={workingTemplate}
                    onChange={(e) => setWorkingTemplate(e.target.value)}
                  />
                )}
              </Field>
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mute">
                  Tokens (click to insert)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {TEMPLATE_TOKENS.map((token) => (
                    <PillTab
                      key={token}
                      onClick={() => appendWorkingToken(token)}
                      ariaLabel={`Insert ${token}`}
                      className="border border-hairline bg-surface-elevated font-mono text-xs text-body hover:bg-surface-card hover:text-on-dark"
                    >
                      {token}
                    </PillTab>
                  ))}
                </div>
              </div>
              <p className="text-xs text-mute">
                {templateModified ? (
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="rounded-xs bg-warning-muted px-1.5 py-0.5 font-medium text-warning">
                      Edited locally
                    </span>
                    <span>Not saved — the preview reflects this working template.</span>
                  </span>
                ) : (
                  "This mirrors the saved Settings template. The preview below reflects exactly what the CLI would produce."
                )}
              </p>
            </div>
          </Panel>

          <Panel title="Generated path" icon={Music}>
            <PathPreview
              path={preview.path}
              errors={preview.errors}
              libraryRoot={savedConfig.paths.library}
            />
          </Panel>
        </div>
      </div>
    </>
  )
}
