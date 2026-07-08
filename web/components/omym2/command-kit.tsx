"use client"

import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "./lib"
import { TONE_DOT_CLASSES, type Tone } from "./primitives"

/* ------------------------------------------------------------------ */
/* Keycap                                                              */
/* ------------------------------------------------------------------ */

/**
 * Inline keyboard-shortcut glyph (e.g. `Ctrl`, `K`, `Enter`, `Esc`). Uses the
 * signature subtle keycap-bg-start → keycap-bg-end gradient for a slight
 * physical-key feel on the flat dark canvas.
 */
export function Keycap({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-xs border border-hairline bg-linear-to-b from-keycap-bg-start to-keycap-bg-end px-2 font-sans text-[13px] leading-[1.4] tracking-[0.1px] text-body",
        className,
      )}
    >
      {children}
    </kbd>
  )
}

/* ------------------------------------------------------------------ */
/* AppIconTile                                                         */
/* ------------------------------------------------------------------ */

const TONE_ICON_CLASSES: Record<Tone, string> = {
  success: "text-success",
  info: "text-info",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-mute",
}

/** Small rounded tile holding a lucide icon (command rows, nav, palette). */
export function AppIconTile({
  icon: Icon,
  size = 32,
  tone,
  className,
}: {
  icon: LucideIcon
  /** Tile edge length in px — DESIGN.md's app-icon-tile vocabulary spans 20-48px. */
  size?: 20 | 24 | 28 | 32 | 40 | 48
  tone?: Tone
  className?: string
}) {
  const iconSizeClass = size <= 24 ? "size-3.5" : size <= 32 ? "size-4" : "size-5"
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-md bg-surface-card",
        tone ? TONE_ICON_CLASSES[tone] : "text-body",
        className,
      )}
      style={{ width: size, height: size }}
    >
      <Icon className={iconSizeClass} aria-hidden="true" />
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* PillTab                                                             */
/* ------------------------------------------------------------------ */

/**
 * Standalone pill-tab filter chip: transparent default, surface-elevated active.
 * Omit `active` for action-style chips (e.g. insert-token buttons) — `aria-pressed`
 * is only emitted when the chip is genuinely a toggle.
 */
export function PillTab({
  active,
  onClick,
  children,
  className,
  ariaLabel,
}: {
  active?: boolean
  onClick?: () => void
  children: ReactNode
  className?: string
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-1 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        active ? "bg-surface-active text-on-dark" : "text-body hover:text-on-dark",
        className,
      )}
    >
      {children}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* CommandRow                                                          */
/* ------------------------------------------------------------------ */

export interface CommandRowProps {
  /** Rendered inside an AppIconTile at the row's leading edge. */
  icon?: LucideIcon
  label: ReactNode
  /** Selection/highlight state — command-palette-row-active treatment. */
  active?: boolean
  /** Trailing hint text (e.g. a status word or "Copied"). */
  hint?: ReactNode
  /** Trailing keycap sequence, e.g. `["Ctrl", "1"]` or `["Enter"]`. */
  keys?: string[]
  /**
   * Status tone dot shown in place of an icon tile when no `icon` is given
   * (e.g. a run's status in the command palette's "Runs" group).
   */
  tone?: Tone
  onSelect?: () => void
  /**
   * ARIA composition: "button" (default) renders a standalone `<button>`
   * for sidebar/nav usage; "option" renders an `<li role="option">` for use
   * inside a `<ul role="listbox">` command-palette result list, where the
   * listbox owner manages focus via `aria-activedescendant`.
   */
  role?: "button" | "option"
  id?: string
  disabled?: boolean
  className?: string
}

/** command-palette-row / command-palette-row-active — also doubles as a nav row. */
export function CommandRow({
  icon: Icon,
  label,
  active = false,
  hint,
  keys,
  tone,
  onSelect,
  role = "button",
  id,
  disabled = false,
  className,
}: CommandRowProps) {
  const content = (
    <>
      <span className="flex min-w-0 flex-1 items-center gap-2.5">
        {Icon ? (
          <AppIconTile icon={Icon} size={24} tone={tone} />
        ) : tone ? (
          <span
            className={cn("size-1.5 shrink-0 rounded-full", TONE_DOT_CLASSES[tone])}
            aria-hidden="true"
          />
        ) : null}
        <span className="min-w-0 flex-1 truncate text-sm text-on-dark">{label}</span>
      </span>
      {hint || (keys && keys.length > 0) ? (
        <span className="flex shrink-0 items-center gap-2 text-xs text-mute">
          {hint ? <span className="truncate">{hint}</span> : null}
          {keys && keys.length > 0 ? (
            <span className="flex items-center gap-1">
              {keys.map((key, index) => (
                <Keycap key={index}>{key}</Keycap>
              ))}
            </span>
          ) : null}
        </span>
      ) : null}
    </>
  )

  const sharedClassName = cn(
    "flex w-full items-center gap-3 rounded-sm px-2.5 py-1.5 text-left transition-colors",
    active ? "bg-surface-active" : "hover:bg-surface-card/70",
    disabled && "pointer-events-none opacity-50",
    className,
  )

  if (role === "option") {
    return (
      <li
        id={id}
        role="option"
        aria-selected={active}
        aria-disabled={disabled || undefined}
        onClick={disabled ? undefined : onSelect}
        className={cn(sharedClassName, "list-none", !disabled && "cursor-pointer")}
      >
        {content}
      </li>
    )
  }

  return (
    <button
      type="button"
      id={id}
      onClick={onSelect}
      disabled={disabled}
      aria-current={active ? "page" : undefined}
      className={cn(sharedClassName, "focus-visible:outline-2 focus-visible:outline-ring")}
    >
      {content}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* ActionBar                                                           */
/* ------------------------------------------------------------------ */

export interface ActionHint {
  /** Keycap sequence, e.g. `["Enter"]` or `["Ctrl", "K"]`. */
  keys: string[]
  label: string
}

/** Bottom contextual hint bar — the primary-nav idiom repurposed as a footer. */
export function ActionBar({ hints, className }: { hints: ActionHint[]; className?: string }) {
  if (hints.length === 0) return null
  return (
    <div
      className={cn(
        "flex items-center gap-4 border-t border-hairline bg-surface-canvas px-4 py-2 text-xs text-mute",
        className,
      )}
    >
      {hints.map((hint, index) => (
        <span key={index} className="flex items-center gap-1.5">
          <span className="flex items-center gap-1">
            {hint.keys.map((key, keyIndex) => (
              <Keycap key={keyIndex}>{key}</Keycap>
            ))}
          </span>
          <span>{hint.label}</span>
        </span>
      ))}
    </div>
  )
}
