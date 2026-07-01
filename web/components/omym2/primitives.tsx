"use client"

import {
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
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

const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-success-muted text-success border-success/30",
  info: "bg-info-muted text-info border-info/30",
  warning: "bg-warning-muted text-warning border-warning/40",
  danger: "bg-danger-muted text-danger border-danger/30",
  neutral: "bg-neutral-muted text-muted-foreground border-border",
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
}: {
  status: string
  tone?: Tone
  label?: string
  className?: string
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
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        TONE_CLASSES[resolved],
        className,
      )}
    >
      <Icon className={cn("size-3.5 shrink-0", spin && "animate-spin")} aria-hidden="true" />
      <span>{label ?? status.replace(/_/g, " ")}</span>
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
        "inline-flex size-7 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-border hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
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
/* Mono / PathDisplay                                                  */
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

export function PathDisplay({
  value,
  max = 48,
  copy = true,
  prefix,
  className,
}: {
  value: string
  max?: number
  copy?: boolean
  prefix?: string
  className?: string
}) {
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1.5", className)}>
      {prefix ? <span className="text-xs text-muted-foreground">{prefix}</span> : null}
      <Mono className="truncate text-foreground">
        <span title={value}>{truncateMiddle(value, max)}</span>
      </Mono>
      {copy ? <CopyButton value={value} label="Copy path" /> : null}
    </span>
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
      <Mono className="truncate text-muted-foreground">
        <span title={source}>{source ? truncateMiddle(source, max) : "—"}</span>
      </Mono>
      <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <Mono className="truncate text-foreground">
        <span title={target}>{target ? truncateMiddle(target, max) : "—"}</span>
      </Mono>
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
    <section
      className={cn(
        "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex items-start gap-2.5">
            {Icon ? (
              <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            ) : null}
            <div>
              {title ? <h2 className="text-sm font-semibold leading-tight">{title}</h2> : null}
              {description ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
              ) : null}
            </div>
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      )}
      <div className={cn("px-4 py-4", bodyClassName)}>{children}</div>
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
      ? "text-foreground"
      : tone === "success"
        ? "text-success"
        : tone === "info"
          ? "text-info"
          : tone === "warning"
            ? "text-warning"
            : "text-danger"
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon ? <Icon className={cn("size-4", accent)} aria-hidden="true" /> : null}
      </div>
      <p className={cn("mt-2 text-2xl font-semibold tabular-nums leading-none", accent)}>{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border px-6 py-10 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-muted">
        <Icon className="size-5 text-muted-foreground" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description ? <p className="max-w-md text-sm text-muted-foreground">{description}</p> : null}
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
    default: "bg-primary text-primary-foreground hover:bg-primary/90 border-transparent",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/70 border-transparent",
    outline: "bg-transparent text-foreground hover:bg-muted border-border",
    ghost:
      "bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground border-transparent",
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
  empty,
  caption,
}: {
  columns: Column<T>[]
  rows: T[]
  getRowKey: (row: T, index: number) => string
  onRowClick?: (row: T) => void
  rowIsActive?: (row: T) => boolean
  empty?: ReactNode
  caption?: string
}) {
  const [colWidths, setColWidths] = useState<Record<string, number>>({})
  const draggingCol = useRef<string | null>(null)

  const onHandlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>, key: string) => {
    e.preventDefault()
    e.stopPropagation()
    draggingCol.current = key
    ;(e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId)
  }, [])

  const onHandlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>, key: string) => {
    if (draggingCol.current !== key) return
    // Read from the event before the state updater runs — React nullifies
    // currentTarget asynchronously, causing "cannot read closest of null".
    const th = (e.currentTarget as HTMLDivElement).closest("th")
    const thWidth = th ? th.getBoundingClientRect().width : null
    const dx = e.movementX
    setColWidths((prev) => {
      const current = thWidth ?? prev[key] ?? 120
      return { ...prev, [key]: Math.max(COL_MIN, current + dx) }
    })
  }, [])

  const onHandlePointerUp = useCallback(() => {
    draggingCol.current = null
  }, [])

  if (rows.length === 0 && empty) {
    return <>{empty}</>
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border">
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
          <tr className="border-b border-border bg-muted/60">
            {columns.map((col, i) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "relative whitespace-nowrap px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground overflow-hidden",
                  col.headerClassName,
                )}
                style={colWidths[col.key] ? { width: colWidths[col.key] } : undefined}
              >
                <span className="block truncate pr-3">{col.header}</span>
                {/* resize handle — not shown on the last column */}
                {i < columns.length - 1 && (
                  <div
                    aria-hidden="true"
                    onPointerDown={(e) => onHandlePointerDown(e, col.key)}
                    onPointerMove={(e) => onHandlePointerMove(e, col.key)}
                    onPointerUp={onHandlePointerUp}
                    className="absolute inset-y-0 right-0 w-3 cursor-col-resize select-none flex items-center justify-center group"
                  >
                    <div className="h-4 w-px bg-border group-hover:bg-primary/60 group-active:bg-primary transition-colors" />
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
                  "border-b border-border last:border-0",
                  interactive &&
                    "cursor-pointer transition-colors hover:bg-muted/50 focus-visible:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                  rowIsActive?.(row) && "bg-accent/60",
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
  )
}
