import * as React from "react"

/** A hover/focus hint for an element that already has an accessible name (e.g. `aria-label`).
 * CSS only (`[data-tip]` in index.css), no JS: Radix Tooltip cost 17.6 kB gzip in the main bundle.
 * Pointer devices only (`@media (hover: hover)`); touch users rely on the label. */
function Tip({ label, side = "top", children }: { label: string; side?: "top" | "bottom" | "right"; children: React.ReactElement<Record<string, unknown>> }) {
  return React.cloneElement(children, { "data-tip": label, "data-tip-side": side })
}

export { Tip }
