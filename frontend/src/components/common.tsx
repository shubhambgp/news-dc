import { AlertTriangle, Inbox, RotateCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { ApiError, type ContentType } from '@/lib/api'
import { cn } from '@/lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} />
}

export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="divide-y">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="space-y-2 py-3">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3 w-5/6" />
        </div>
      ))}
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg =
    error instanceof ApiError
      ? error.status === 429
        ? 'Too many requests. Wait a minute and try again.'
        : error.message
      : 'Something went wrong.'
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center">
      <AlertTriangle className="size-6 text-destructive" aria-hidden />
      <p className="text-sm">{msg}</p>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          <RotateCw /> Retry
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      <Inbox className="size-6" aria-hidden />
      {children}
    </div>
  )
}

const TYPE_STYLE: Record<ContentType, string> = {
  news: 'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200',
  research: 'bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200',
  investment: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  engineering: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
}

export function TypeBadge({ type }: { type: ContentType | null }) {
  if (!type) return null
  return <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-medium capitalize', TYPE_STYLE[type])}>{type}</span>
}

/** Quality as a 5-step bar, with the number for screen readers and on hover. */
export function Quality({ score }: { score: number | null }) {
  if (score == null) return null
  const filled = Math.round(score / 20)
  return (
    <span className="inline-flex items-center gap-0.5" title={`Quality ${score}/100`}>
      <span className="sr-only">Quality {score} out of 100</span>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} aria-hidden className={cn('h-2.5 w-1 rounded-sm', i < filled ? 'bg-primary' : 'bg-muted-foreground/25')} />
      ))}
    </span>
  )
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      {children}
    </div>
  )
}
