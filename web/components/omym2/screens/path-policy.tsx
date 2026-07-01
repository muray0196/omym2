"use client"

import { Braces, Music, RotateCcw } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { TEMPLATE_TOKENS, renderPath } from "../lib"
import type { SampleMetadata } from "../types"
import { Button, Mono, Panel } from "../primitives"
import { Field, Select, TextArea, TextInput } from "../forms"
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
  { key: "track_number", label: "Track no." },
  { key: "extension", label: "Extension" },
]

export function PathPolicyScreen() {
  const { savedConfig } = useApp()
  const policy = savedConfig.path_policy

  const [presetId, setPresetId] = useState(SAMPLE_PRESETS[0].id)
  const [meta, setMeta] = useState<SampleMetadata>(SAMPLE_PRESETS[0].meta)

  function selectPreset(id: string) {
    setPresetId(id)
    const preset = SAMPLE_PRESETS.find((p) => p.id === id)
    if (preset) setMeta(preset.meta)
  }

  function updateMeta(key: keyof SampleMetadata, value: string) {
    setMeta((prev) => ({ ...prev, [key]: value }))
    setPresetId("custom")
  }

  const preview = useMemo(() => renderPath(policy.template, meta, policy), [policy, meta])

  return (
    <>
      <PageHeading
        title="Path policy preview"
        description="See how the saved path policy turns track metadata into a canonical relative path. The template and fallbacks are configured in Settings; this screen previews them against sample metadata."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <Panel
            title="Active policy"
            icon={Braces}
            description="Read-only. Edit these values in Settings."
          >
            <dl className="flex flex-col gap-3 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">Template</dt>
                <dd className="mt-1">
                  <Mono className="break-all text-foreground">{policy.template}</Mono>
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    Unknown artist
                  </dt>
                  <dd className="font-medium">{policy.unknown_artist}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    Unknown album
                  </dt>
                  <dd className="font-medium">{policy.unknown_album}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    Max filename length
                  </dt>
                  <dd className="font-medium tabular-nums">{policy.max_filename_length}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    Sanitize segments
                  </dt>
                  <dd className="font-medium">{policy.sanitize ? "Enabled" : "Disabled"}</dd>
                </div>
              </div>
              <div>
                <dt className="mb-1.5 text-xs uppercase tracking-wide text-muted-foreground">
                  Available tokens
                </dt>
                <dd className="flex flex-wrap gap-1.5">
                  {TEMPLATE_TOKENS.map((token) => (
                    <span
                      key={token}
                      className="rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground"
                    >
                      {token}
                    </span>
                  ))}
                </dd>
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
              <Field label="Preset">
                {(id) => (
                  <Select
                    id={id}
                    value={presetId}
                    onChange={(e) => selectPreset(e.target.value)}
                    options={[
                      ...SAMPLE_PRESETS.map((p) => ({ value: p.id, label: p.label })),
                      { value: "custom", label: "Custom (edited)" },
                    ]}
                  />
                )}
              </Field>
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
          >
            <Field
              label="Working template"
              help="Templates must not include a file extension; the source extension is appended automatically."
            >
              {(id) => <TextArea id={id} mono rows={2} value={policy.template} readOnly />}
            </Field>
            <p className="mt-2 text-xs text-muted-foreground">
              This mirrors the saved Settings template. The preview below reflects exactly what the
              CLI would produce.
            </p>
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
