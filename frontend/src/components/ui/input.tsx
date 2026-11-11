import * as React from "react"
import { cn } from "cn"

/** Shared field look: inputs, textareas and native selects (kept native for accessibility). */
const field =
  "w-full min-w-0 rounded-lg border border-input bg-surface text-sm text-foreground shadow-card transition-colors placeholder:text-muted-foreground hover:border-foreground/25 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive"

function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input data-slot="input" className={cn(field, "h-10 px-3 md:h-9", className)} {...props} />
}

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(field, "min-h-20 px-3 py-2.5 leading-relaxed", className)} {...props} />
}

/** Native `<select>` with a drawn chevron; the OS picker follows `color-scheme`. */
function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        field,
        "h-10 cursor-pointer appearance-none bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")] bg-[length:16px] bg-[right_0.6rem_center] bg-no-repeat pr-8 pl-3 md:h-9",
        className
      )}
      {...props}
    />
  )
}

export { Input, Select, Textarea, field as fieldClass }
