import * as React from "react"
import { cn } from "cn"

type Option<T extends string> = readonly [value: T, content: React.ReactNode, ariaLabel?: string]

/** A small set of mutually exclusive choices (time window, sort, view). Buttons with
 * `aria-pressed` in a labelled group: simple for screen readers and keyboard users. */
function Segmented<T extends string>({ label, value, options, onChange, className }: { label: string; value: T; options: readonly Option<T>[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex shrink-0 rounded-lg border bg-surface p-0.5 shadow-card", className)}>
      {options.map(([v, content, aria]) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          aria-label={aria}
          onClick={() => onChange(v)}
          className={cn(
            "inline-flex h-8 min-w-9 items-center justify-center gap-1.5 rounded-md px-2.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:h-7 [&_svg]:size-4",
            v === value ? "bg-primary text-primary-foreground shadow-card" : "text-muted-foreground hover:bg-elevated hover:text-foreground"
          )}
        >
          {content}
        </button>
      ))}
    </div>
  )
}

export { Segmented }
