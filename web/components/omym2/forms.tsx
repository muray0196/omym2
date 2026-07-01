"use client"

import { useId, type ReactNode } from "react"
import { cn } from "./lib"

export function Field({
  label,
  help,
  children,
  htmlFor,
  className,
}: {
  label: ReactNode
  help?: ReactNode
  children: (id: string) => ReactNode
  htmlFor?: string
  className?: string
}) {
  const generated = useId()
  const id = htmlFor ?? generated
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children(id)}
      {help ? <p className="text-xs leading-relaxed text-muted-foreground">{help}</p> : null}
    </div>
  )
}

const controlClasses =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring/40"

export function TextInput({
  className,
  mono,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }) {
  return (
    <input
      className={cn(controlClasses, mono && "font-mono text-[0.8125rem]", className)}
      {...props}
    />
  )
}

export function TextArea({
  className,
  mono,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { mono?: boolean }) {
  return (
    <textarea
      className={cn(controlClasses, "resize-y", mono && "font-mono text-[0.8125rem]", className)}
      {...props}
    />
  )
}

export function Select({
  className,
  options,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string; label: string }[]
}) {
  return (
    <select className={cn(controlClasses, "cursor-pointer", className)} {...props}>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  help,
  id: providedId,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: ReactNode
  help?: ReactNode
  id?: string
}) {
  const generated = useId()
  const id = providedId ?? generated
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-border bg-background px-3 py-2.5">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        {help ? <p className="mt-0.5 text-xs text-muted-foreground">{help}</p> : null}
      </div>
      <button
        type="button"
        role="switch"
        id={id}
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          checked ? "border-primary bg-primary" : "border-input bg-muted",
        )}
      >
        <span
          className={cn(
            "inline-block size-4 transform rounded-full bg-background shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  )
}
