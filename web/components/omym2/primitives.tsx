/*
Summary: Defines shared UI primitives for the OMYM2 console.
Why: Keeps table, panel, status, and control behavior consistent across screens.
*/

"use client"

import {
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  ChevronDown,
  Copy,
  Info,
  LoaderCircle,
  ArrowRight,
} from "lucide-react"
import { useCallback, useRef, useState, type ReactNode } from "react"
import { cn, truncateMiddle } from "./lib"

/* ------------------------------------------------------------------ */
/* Tone system                                                         */
/* ------------------------------------------------------------------ */

export type Tone = "success" | "info" | "warning" | "danger" | "neutral"

/**
 * badge-info-soft pattern: soft 15%-alpha accent fill + saturated accent
 * text (the only place saturated accent color appears on chrome). Neutral
 * uses the badge-pro pattern instead: surface-elevated fill + mute text +
 * hairline border.
 */
const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-success-muted text-success border-transparent",
  info: "bg-info-muted text-info border-transparent",
  warning: "bg-warning-muted text-warning border-transparent",
  danger: "bg-danger-muted text-danger border-transparent",
  neutral: "bg-surface-elevated text-mute border-hairline",
}

const STATUS_TONE: Record<string, Tone> = {
  // runs / plans / events
  succeeded: "success",
  applied: "success",
  active: "success",
  registered: "success",
  valid: "success",
  running: "info",
  applying: "info",
  ready: "info",
  pending: "info",
  partial_failed: "warning",
  stale: "warning",
  planned: "warning",
  blocked: "danger",
  failed: "danger",
  removed: "danger",
  cancelled: "danger",
  expired: "danger",
  invalid: "danger",
  // severities
  info: "info",
  warning: "warning",
  error: "danger",
}

export function toneForStatus(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral"
}

/** Solid tone dot, no border (e.g. command palette result markers). */
export const TONE_DOT_CLASSES: Record<Tone, string> = {
  success: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-mute",
}

/** Bordered tone dot (e.g. timeline status markers). */
export const TONE_MARKER_CLASSES: Record<Tone, string> = {
  success: "border-success bg-success",
  info: "border-info bg-info",
  warning: "border-warning bg-warning",
  danger: "border-danger bg-danger",
  neutral: "border-hairline bg-mute",
}

/** Humanize a snake_case status/label for display. */
export function truncateLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
}

/* ------------------------------------------------------------------ */
/* StatusBadge                                                         */
/* ------------------------------------------------------------------ */

export function StatusBadge({
  status,
  tone,
  label,
  className,
  iconOnly = false,
}: {
  status: string
  tone?: Tone
  label?: string
  className?: string
  /** Render only the status icon; the label is exposed to assistive tech and a tooltip. */
  iconOnly?: boolean
}) {
  const resolved = tone ?? toneForStatus(status)
  const Icon =
    resolved === "success"
      ? CircleCheck
      : resolved === "danger"
        ? CircleX
        : resolved === "warning"
          ? CircleAlert
          : resolved === "info"
            ? status === "running" || status === "applying"
              ? LoaderCircle
              : Info
            : Info
  const spin = status === "running" || status === "applying"
  const text = label ?? status.replace(/_/g, " ")
  if (iconOnly) {
    return (
      <span
        className={cn(
          "inline-flex size-6 items-center justify-center rounded-md border",
          TONE_CLASSES[resolved],
          className,
        )}
        title={text}
      >
        <Icon className={cn("size-3.5 shrink-0", spin && "animate-spin")} aria-hidden="true" />
        <span className="sr-only">{text}</span>
      </span>
    )
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        TONE_CLASSES[resolved],
        className,
      )}
    >
      <Icon className={cn("size-3.5 shrink-0", spin && "animate-spin")} aria-hidden="true" />
      <span>{text}</span>
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* CopyButton                                                          */
/* ------------------------------------------------------------------ */

export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string
  label?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      // ignore clipboard failures in prototype
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        "inline-flex size-7 items-center justify-center rounded-md border border-transparent text-mute transition-colors hover:border-hairline hover:bg-surface-elevated hover:text-on-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
      aria-label={copied ? `${label}: copied` : label}
      title={label}
    >
      {copied ? (
        <Check className="size-3.5 text-success" aria-hidden="true" />
      ) : (
        <Copy className="size-3.5" aria-hidden="true" />
      )}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Mono / PathArrow                                                    */
/* ------------------------------------------------------------------ */

export function Mono({
  children,
  className,
  title,
}: {
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <code className={cn("font-mono text-[0.8125rem] tracking-tight", className)} title={title}>
      {children}
    </code>
  )
}

export function PathArrow({
  source,
  target,
  max = 40,
}: {
  source: string
  target: string
  max?: number
}) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
      <Mono className="truncate text-mute">
        <span title={source}>{source ? truncateMiddle(source, max) : "—"}</span>
      </Mono>
      <ArrowRight className="size-3.5 shrink-0 text-mute" aria-hidden="true" />
      <Mono className="truncate text-ink">
        <span title={target}>{target ? truncateMiddle(target, max) : "—"}</span>
      </Mono>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* MetaRow                                                             */
/* ------------------------------------------------------------------ */

/**
 * One label/value row inside a <dl>. Pass `value` for the common case (a
 * mono, middle-truncated, optionally copyable string). Pass `children`
 * instead when the caller needs full control over the value cell (e.g.
 * break-all paths, composed numbers) rather than truncation.
 * `responsive` stacks label above value below `sm` — used by detail lists
 * that read better full-width on narrow screens.
 */
export function MetaRow({
  label,
  value,
  children,
  copy = false,
  max = 36,
  responsive = false,
}: {
  label: string
  value?: string
  children?: ReactNode
  copy?: boolean
  max?: number
  responsive?: boolean
}) {
  return (
    <div
      className={cn(
        "border-b border-hairline py-2 last:border-0",
        responsive
          ? "flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
          : "flex items-center justify-between gap-3",
      )}
    >
      <dt className="text-xs uppercase tracking-wide text-mute">{label}</dt>
      {value !== undefined ? (
        <dd className="flex min-w-0 items-center gap-1">
          <Mono className="truncate text-ink" title={value}>
            {truncateMiddle(value, max)}
          </Mono>
          {copy ? <CopyButton value={value} label={`Copy ${label}`} /> : null}
        </dd>
      ) : (
        <dd className="min-w-0 text-sm">{children}</dd>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Panel / Card                                                        */
/* ------------------------------------------------------------------ */

export function Panel({
  title,
  description,
  actions,
  icon: Icon,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  icon?: typeof Info
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cn("rounded-lg border border-hairline bg-surface text-ink", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-3.5">
          <div className="flex items-start gap-2.5">
            {Icon ? <Icon className="mt-0.5 size-4 shrink-0 text-mute" aria-hidden="true" /> : null}
            <div>
              {title ? <h2 className="text-sm font-semibold leading-tight">{title}</h2> : null}
              {description ? <p className="mt-0.5 text-xs text-mute">{description}</p> : null}
            </div>
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      )}
      <div className={cn("px-5 py-5", bodyClassName)}>{children}</div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* MetricCard                                                          */
/* ------------------------------------------------------------------ */

export function MetricCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon: Icon,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: Tone
  icon?: typeof Info
}) {
  const accent =
    tone === "neutral"
      ? "text-ink"
      : tone === "success"
        ? "text-success"
        : tone === "info"
          ? "text-info"
          : tone === "warning"
            ? "text-warning"
            : "text-danger"
  return (
    <div className="rounded-lg border border-hairline bg-surface p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-mute">{label}</p>
        {Icon ? <Icon className={cn("size-4", accent)} aria-hidden="true" /> : null}
      </div>
      <p className={cn("mt-2 text-2xl font-semibold tabular-nums leading-none", accent)}>{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-mute">{hint}</p> : null}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Notice / ErrorBanner                                                */
/* ------------------------------------------------------------------ */

export function Notice({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone
  title?: ReactNode
  children?: ReactNode
  className?: string
}) {
  const Icon =
    tone === "success"
      ? CircleCheck
      : tone === "danger"
        ? CircleX
        : tone === "warning"
          ? CircleAlert
          : Info
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? (
          <div className={cn("text-[0.8125rem]", title ? "mt-0.5" : "")}>{children}</div>
        ) : null}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* EmptyState                                                          */
/* ------------------------------------------------------------------ */

export function EmptyState({
  icon: Icon = Info,
  title,
  description,
  children,
}: {
  icon?: typeof Info
  title: string
  description?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-hairline px-6 py-10 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-surface-card">
        <Icon className="size-5 text-mute" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? <p className="max-w-md text-sm text-mute">{description}</p> : null}
      {children}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Button / inputs                                                     */
/* ------------------------------------------------------------------ */

export function Button({
  variant = "default",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "outline" | "ghost"
  size?: "sm" | "md"
}) {
  const variants = {
    // button-primary — the one white pill per fold.
    default:
      "bg-primary text-primary-foreground hover:bg-primary-pressed active:bg-primary-pressed border-transparent",
    // button-tertiary — soft surface fill.
    secondary: "bg-surface-elevated text-on-dark hover:bg-surface-card border-transparent",
    // install-button — transparent + hairline-strong border.
    outline: "bg-transparent text-on-dark border-hairline-strong hover:bg-surface-elevated",
    // button-secondary — transparent text button.
    ghost:
      "bg-transparent text-mute hover:bg-surface-elevated hover:text-on-dark border-transparent",
  }
  const sizes = { sm: "h-8 px-2.5 text-xs", md: "h-9 px-3.5 text-sm" }
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  )
}

/* ------------------------------------------------------------------ */
/* SegmentedControl                                                    */
/* ------------------------------------------------------------------ */

export interface SegmentedOption<T extends string> {
  value: T
  label: ReactNode
  icon?: typeof Info
}

/**
 * Shared segmented button-group, styled as a row of pill-tab chips (rounded
 * full, transparent default, active = surface-elevated fill + on-dark text).
 * Two flavors share this one visual language:
 *  - "picker" (default): a value picker — renders aria-pressed on a
 *    role="group" container. Use for mutually-exclusive view/mode toggles.
 *  - "nav": in-page navigation between sections — renders aria-current on
 *    a <nav> landmark instead of aria-pressed on a group.
 */
export function SegmentedControl<T extends string>({
  ariaLabel,
  options,
  value,
  onChange,
  variant = "picker",
  size = "md",
  className,
}: {
  ariaLabel: string
  options: SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
  variant?: "picker" | "nav"
  size?: "sm" | "md"
  className?: string
}) {
  const sizeClasses = size === "sm" ? "gap-1.5 px-2.5 py-1 text-xs" : "min-h-9 gap-1.5 px-3 text-sm"
  const iconSize = size === "sm" ? "size-3.5" : "size-4"
  const trackClassName = cn("flex flex-wrap items-center gap-1", className)

  const items = options.map((option) => {
    const active = option.value === value
    const Icon = option.icon
    return (
      <button
        key={option.value}
        type="button"
        onClick={() => onChange(option.value)}
        aria-pressed={variant === "picker" ? active : undefined}
        aria-current={variant === "nav" ? (active ? "true" : undefined) : undefined}
        className={cn(
          "flex items-center justify-center whitespace-nowrap rounded-full font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          sizeClasses,
          active ? "bg-surface-active text-on-dark" : "text-body hover:text-on-dark",
        )}
      >
        {Icon ? <Icon className={cn(iconSize, "shrink-0")} aria-hidden="true" /> : null}
        {option.label}
      </button>
    )
  })

  if (variant === "nav") {
    return (
      <nav aria-label={ariaLabel} className={trackClassName}>
        {items}
      </nav>
    )
  }
  return (
    <div role="group" aria-label={ariaLabel} className={trackClassName}>
      {items}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* DataTable                                                           */
/* ------------------------------------------------------------------ */

export interface Column<T> {
  key: string
  header: ReactNode
  cell: (row: T) => ReactNode
  className?: string
  headerClassName?: string
}

const COL_MIN = 60

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  onRowClick,
  rowIsActive,
  rowActiveClassName = "bg-accent",
  empty,
  caption,
  loadMore,
}: {
  columns: Column<T>[]
  rows: T[]
  getRowKey: (row: T, index: number) => string
  onRowClick?: (row: T) => void
  rowIsActive?: (row: T) => boolean
  /**
   * Fill applied when `rowIsActive(row)` is true. Defaults to the existing
   * status-highlight tone (e.g. blocked/failed rows) — pass "bg-surface-active"
   * for genuine row-selection use cases (e.g. the currently viewed track) so
   * selection reads brighter than a status tone.
   */
  rowActiveClassName?: string
  empty?: ReactNode
  caption?: string
  loadMore?: {
    hasMore: boolean
    loading?: boolean
    onLoadMore: () => void
    total?: number | null
  }
}) {
  const [colWidths, setColWidths] = useState<Record<string, number>>({})
  const drag = useRef<{
    leftKey: string
    rightKey: string
    startX: number
    leftStart: number
    rightStart: number
  } | null>(null)

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>, key: string, nextKey: string) => {
      e.preventDefault()
      e.stopPropagation()
      try {
        ;(e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId)
      } catch {
        // Ignore: pointer capture can fail for non-active pointers (e.g. tests).
      }
      // Measure the two adjacent columns so we can redistribute width between
      // them only, leaving all other columns untouched.
      const headerRow = (e.currentTarget as HTMLDivElement).closest("tr")
      let leftStart = 120
      let rightStart = 120
      const measured: Record<string, number> = {}
      if (headerRow) {
        headerRow.querySelectorAll<HTMLTableCellElement>("th[data-col-key]").forEach((th) => {
          const k = th.dataset.colKey
          if (!k) return
          const w = th.getBoundingClientRect().width
          measured[k] = w
          if (k === key) leftStart = w
          if (k === nextKey) rightStart = w
        })
      }
      drag.current = { leftKey: key, rightKey: nextKey, startX: e.clientX, leftStart, rightStart }
      // Lock all columns to their current widths so table-layout: fixed has
      // explicit values to work with before the first move event arrives.
      setColWidths((prev) => ({ ...measured, ...prev }))
    },
    [],
  )

  const onHandlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    const delta = e.clientX - d.startX
    // Clamp each side independently, then use only the effective delta that
    // was actually applied so that when one column bottoms out at COL_MIN the
    // other side stops moving too instead of continuing to grow.
    const unclamped = d.leftStart + delta
    const newLeft = Math.max(COL_MIN, Math.min(unclamped, d.leftStart + d.rightStart - COL_MIN))
    const newRight = d.leftStart + d.rightStart - newLeft
    setColWidths((prev) => {
      if (prev[d.leftKey] === newLeft && prev[d.rightKey] === newRight) return prev
      return { ...prev, [d.leftKey]: newLeft, [d.rightKey]: newRight }
    })
  }, [])

  const onHandlePointerUp = useCallback(() => {
    drag.current = null
  }, [])

  const totalCount = loadMore?.total ?? null
  const showingCount = totalCount === null ? rows.length : Math.min(rows.length, totalCount)
  const loadMoreFooter = loadMore ? (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 bg-surface-elevated px-3 py-2.5",
        rows.length === 0 ? "rounded-md border border-hairline" : "border-t border-hairline",
      )}
    >
      <span className="text-xs tabular-nums text-mute">
        {totalCount === null
          ? `${showingCount} row${showingCount === 1 ? "" : "s"} loaded`
          : `${showingCount} of ${totalCount} row${totalCount === 1 ? "" : "s"} loaded`}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={!loadMore.hasMore || loadMore.loading}
        onClick={loadMore.onLoadMore}
      >
        <ChevronDown className="size-4" aria-hidden="true" />
        {loadMore.loading ? "Loading..." : loadMore.hasMore ? "Load more" : "All rows loaded"}
      </Button>
    </div>
  ) : null

  if (rows.length === 0 && empty) {
    return (
      <div className="flex flex-col gap-3">
        {empty}
        {loadMore?.hasMore || loadMore?.loading ? loadMoreFooter : null}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-md border border-hairline">
      <div className="overflow-x-auto">
        <table className="border-collapse text-sm" style={{ tableLayout: "fixed", width: "100%" }}>
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <colgroup>
            {columns.map((col) =>
              colWidths[col.key] ? (
                <col key={col.key} style={{ width: colWidths[col.key] }} />
              ) : (
                <col key={col.key} />
              ),
            )}
          </colgroup>
          <thead>
            <tr className="border-b border-hairline bg-surface-elevated">
              {columns.map((col, i) => (
                <th
                  key={col.key}
                  scope="col"
                  data-col-key={col.key}
                  className={cn(
                    "relative whitespace-nowrap px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-mute overflow-hidden",
                    col.headerClassName,
                  )}
                  style={colWidths[col.key] ? { width: colWidths[col.key] } : undefined}
                >
                  <span className="block truncate pr-3">{col.header}</span>
                  {/* resize handle — not shown on the last column */}
                  {i < columns.length - 1 && (
                    <div
                      aria-hidden="true"
                      onPointerDown={(e) => onHandlePointerDown(e, col.key, columns[i + 1].key)}
                      onPointerMove={onHandlePointerMove}
                      onPointerUp={onHandlePointerUp}
                      onPointerCancel={onHandlePointerUp}
                      className="absolute inset-y-0 right-0 w-3 cursor-col-resize select-none flex items-center justify-center group"
                    >
                      <div className="h-4 w-px bg-hairline-strong group-hover:bg-primary/60 group-active:bg-primary transition-colors" />
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const interactive = Boolean(onRowClick)
              return (
                <tr
                  key={getRowKey(row, index)}
                  onClick={interactive ? () => onRowClick?.(row) : undefined}
                  onKeyDown={
                    interactive
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            onRowClick?.(row)
                          }
                        }
                      : undefined
                  }
                  tabIndex={interactive ? 0 : undefined}
                  role={interactive ? "button" : undefined}
                  className={cn(
                    "border-b border-hairline last:border-0",
                    interactive &&
                      "cursor-pointer transition-colors hover:bg-surface-card/60 focus-visible:bg-surface-card focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                    rowIsActive?.(row) && rowActiveClassName,
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn("overflow-hidden px-3 py-2.5 align-middle", col.className)}
                    >
                      {col.cell(row)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {loadMoreFooter}
    </div>
  )
}
