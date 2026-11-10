import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

// Tinted badges use the `*-ink` text tokens, which keep AA contrast on the 12% tint in both themes.
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-md border border-transparent px-1.5 py-0.5 text-2xs font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "bg-elevated text-foreground/85",
        primary: "bg-primary/12 text-primary-ink",
        ai: "bg-ai/12 text-ai-ink",
        data: "bg-data/12 text-data-ink",
        success: "bg-success/12 text-success-ink",
        warning: "bg-warning/14 text-warning-ink",
        destructive: "bg-destructive/12 text-destructive-ink",
        outline: "border-border text-foreground [a&]:hover:bg-elevated",
        // On category artwork (always dark), so fixed white.
        overlay: "rounded-full bg-black/40 px-2.5 text-white backdrop-blur-sm [a&]:min-h-6 [a&]:py-1 [a&]:hover:bg-black/55",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
)

function Badge({
  className,
  variant = "neutral",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
