"use client"

import type { ReactNode } from "react"

export function PageHeading({
  title,
  description,
  actions,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        {/* heading-lg: 22px/500/1.15, holds body-sm mute description below. */}
        <h1 className="text-pretty text-[22px] font-medium leading-[1.15] text-ink lg:text-2xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-1.5 max-w-2xl text-pretty text-sm leading-relaxed text-mute">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  )
}
