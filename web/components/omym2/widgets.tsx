"use client"

import { ArrowRight, FolderTree } from "lucide-react"
import type { ConfigDiffRow } from "./lib"
import { cn, formatTimestamp } from "./lib"
import type { FileEvent } from "./types"
import {
  CopyButton,
  EmptyState,
  Mono,
  Notice,
  StatusBadge,
  TONE_MARKER_CLASSES,
  toneForStatus,
} from "./primitives"

/* ChangeDiff: before/after table of changed config fields. */
export function ChangeDiff({ rows }: { rows: ConfigDiffRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
        No pending changes.
      </p>
    )
  }
  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Pending configuration changes</caption>
        <thead>
          <tr className="border-b border-border bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" className="px-3 py-2 font-semibold">
              Field
            </th>
            <th scope="col" className="px-3 py-2 font-semibold">
              Before
            </th>
            <th scope="col" className="px-3 py-2 font-semibold">
              After
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field} className="border-b border-border last:border-0 align-top">
              <td className="px-3 py-2">
                <Mono className="text-muted-foreground">{row.field}</Mono>
              </td>
              <td className="px-3 py-2">
                <Mono className="text-danger line-through decoration-danger/40">{row.before}</Mono>
              </td>
              <td className="px-3 py-2">
                <Mono className="text-success">{row.after}</Mono>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* PathTree: visualize a relative path as an indented folder tree. */
export function PathTree({ path, libraryRoot }: { path: string; libraryRoot: string | null }) {
  const segments = path.split("/").filter(Boolean)
  return (
    <ol className="flex flex-col font-mono text-[0.8125rem] leading-6" aria-label="Path segments">
      {libraryRoot ? (
        <li className="text-muted-foreground">
          <span title={libraryRoot}>{libraryRoot}</span>
        </li>
      ) : null}
      {segments.map((segment, index) => {
        const isFile = index === segments.length - 1
        const indentUnits = index + (libraryRoot ? 1 : 0)
        return (
          <li key={`${index}-${segment}`} className="flex items-center whitespace-nowrap">
            <span className="select-none text-muted-foreground/60" aria-hidden="true">
              {"\u00A0\u00A0".repeat(indentUnits)}
              {"└─ "}
            </span>
            <span
              className={cn(
                "min-w-0 truncate",
                isFile ? "font-medium text-foreground" : "text-foreground/80",
              )}
              title={segment}
            >
              {segment}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/* PathPreview: render a generated canonical relative path with errors. */
export function PathPreview({
  path,
  errors,
  libraryRoot,
}: {
  path: string | null
  errors: string[]
  libraryRoot: string | null
}) {
  return (
    <div className="flex flex-col gap-3">
      {path ? (
        <div className="rounded-md border border-border bg-muted/40 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Canonical relative path
            </span>
            <CopyButton value={path} label="Copy canonical path" />
          </div>
          <div className="flex items-start gap-2">
            <FolderTree
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <Mono className="break-all text-foreground">{path}</Mono>
          </div>
          <div className="mt-3 overflow-x-auto rounded border border-border bg-background/60 px-3 py-2">
            <PathTree path={path} libraryRoot={libraryRoot} />
          </div>
        </div>
      ) : null}

      {errors.length > 0 ? (
        <Notice tone="danger" title="Preview errors">
          <ul className="list-inside list-disc space-y-0.5">
            {errors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {!path && errors.length === 0 ? (
        <p className="text-sm text-muted-foreground">Enter metadata to preview the path.</p>
      ) : null}
    </div>
  )
}

/* RunTimeline: vertical timeline summarizing recorded file events. */
export function RunTimeline({ events }: { events: FileEvent[] }) {
  if (events.length === 0) {
    return <EmptyState icon={FolderTree} title="No file events were recorded." />
  }
  return (
    <ol className="relative flex flex-col gap-0 pl-1">
      {events.map((event, index) => {
        const markerClass = TONE_MARKER_CLASSES[toneForStatus(event.status)]
        const isLast = index === events.length - 1
        return (
          <li key={event.event_id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn("mt-1 size-3 shrink-0 rounded-full border-2", markerClass)}
                aria-hidden="true"
              />
              {!isLast ? <span className="w-px flex-1 bg-border" aria-hidden="true" /> : null}
            </div>
            <div className="min-w-0 flex-1 pb-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold tabular-nums text-muted-foreground">
                  #{event.sequence_no}
                </span>
                <span className="text-sm font-medium">{event.event_type.replace(/_/g, " ")}</span>
                <StatusBadge status={event.status} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                {event.source_path ? (
                  <>
                    <Mono className="text-muted-foreground" title={event.source_path}>
                      {event.source_path}
                    </Mono>
                    <ArrowRight className="size-3 text-muted-foreground" aria-hidden="true" />
                  </>
                ) : null}
                <Mono className="text-foreground" title={event.target_path}>
                  {event.target_path || "—"}
                </Mono>
              </div>
              {event.error_message ? (
                <p className="mt-1 text-xs text-danger">
                  <span className="font-mono font-medium">{event.error_code}</span>{" "}
                  {event.error_message}
                </p>
              ) : null}
              <p className="mt-1 text-xs text-muted-foreground">
                {formatTimestamp(event.started_at)}
                {event.completed_at ? ` → ${formatTimestamp(event.completed_at)}` : ""}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/* CliCommand: copyable guidance card (never an execution button). */
export function CliCommand({
  command,
  description,
  className,
}: {
  command: string
  description?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-md border border-border bg-muted/50 px-3 py-2",
        className,
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="select-none font-mono text-xs text-muted-foreground">$</span>
          <Mono className="truncate text-foreground" title={command}>
            {command}
          </Mono>
        </div>
        {description ? <p className="mt-0.5 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      <CopyButton value={command} label="Copy command" />
    </div>
  )
}
