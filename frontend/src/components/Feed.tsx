import { useInfiniteQuery } from '@tanstack/react-query'
import { LayoutGrid, List, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { FeaturedCard } from '@/components/ArticleCards'
import { CardGrid, CardSkeleton, EmptyState, ErrorState, Skeleton } from '@/components/common'
import { ItemCard, type CardLayout } from '@/components/ItemCard'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { CONTENT_TYPES, type ItemSummary, type Page } from '@/lib/api'
import { useCategories, useSources } from '@/lib/format'
import { useSetParam, useView } from '@/lib/filters'
import { useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

const FILTER_KEYS = ['category', 'content_type', 'source', 'min_quality', 'from', 'to'] as const

export function ViewToggle() {
  const [view, setView] = useView()
  return (
    <Segmented
      label="Layout"
      value={view}
      onChange={setView}
      options={[
        ['card', <LayoutGrid key="g" aria-hidden />, 'Card grid'],
        ['row', <List key="l" aria-hidden />, 'Compact list'],
      ]}
    />
  )
}

/** Filter toolbar. Row 1: content type chips and `toolbar` (sort, view). Row 2: category, source,
 * quality and `children` (e.g. dates); on phones row 2 opens from a "Filters" button. */
export function Filters({ hideCategory, children, toolbar }: { hideCategory?: boolean; children?: ReactNode; toolbar?: ReactNode }) {
  const [sp, set] = useSetParam()
  const [, setSp] = useSearchParams()
  const { topics } = useCategories()
  const sources = useSources()
  const [open, setOpen] = useState(false)
  const type = sp.get('content_type') ?? ''
  const active = FILTER_KEYS.filter((k) => sp.get(k) && !(hideCategory && k === 'category')).length
  const clear = () =>
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const k of FILTER_KEYS) if (!(hideCategory && k === 'category')) next.delete(k)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  const extra = active - (type ? 1 : 0)

  return (
    <form role="search" aria-label="Filters" className="mb-4 rounded-xl border bg-surface p-2.5 shadow-card" onSubmit={(e) => e.preventDefault()}>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Content type" className="-mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto px-1 py-0.5">
          {['', ...CONTENT_TYPES].map((t) => (
            <button
              key={t || 'all'}
              type="button"
              aria-pressed={type === t}
              onClick={() => set('content_type', t)}
              className={cn(
                'h-8 shrink-0 rounded-full px-3 text-sm font-medium capitalize transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                type === t ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-elevated hover:text-foreground',
              )}
            >
              {t || 'All'}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="md:hidden" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            <SlidersHorizontal /> Filters{extra > 0 && <span className="rounded-full bg-primary px-1.5 text-2xs text-primary-foreground">{extra}</span>}
          </Button>
          {toolbar}
        </div>
      </div>
      <div className={cn('mt-2.5 grid grid-cols-2 items-center gap-2 border-t pt-2.5 md:flex md:flex-wrap', !open && 'max-md:hidden')}>
        {!hideCategory && (
          <Select aria-label="Category" className="md:w-52" value={sp.get('category') ?? ''} onChange={(e) => set('category', e.target.value)}>
            <option value="">All categories</option>
            {topics.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </Select>
        )}
        <Select aria-label="Source" className="md:w-48" value={sp.get('source') ?? ''} onChange={(e) => set('source', e.target.value)}>
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s.key} value={s.key}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select aria-label="Minimum quality" className="md:w-40" value={sp.get('min_quality') ?? ''} onChange={(e) => set('min_quality', e.target.value)}>
          <option value="">Any quality</option>
          {[40, 60, 70, 80].map((q) => (
            <option key={q} value={q}>
              Quality ≥ {q}
            </option>
          ))}
        </Select>
        {children}
        {active > 0 && (
          <Button type="button" variant="ghost" size="sm" onClick={clear} className="col-span-2 justify-self-start text-muted-foreground md:ml-auto">
            <X /> Clear filters ({active})
          </Button>
        )}
      </div>
    </form>
  )
}

function RowSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="space-y-3">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex gap-4 rounded-xl border bg-surface p-3 shadow-card">
          <Skeleton className="h-24 w-28 shrink-0 sm:w-40" />
          <div className="flex-1 space-y-2 py-1">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  )
}

type FeedProps<T extends ItemSummary> = {
  queryKey: unknown[]
  fetchPage: (page: number) => Promise<Page<T>>
  render?: (item: T, layout: CardLayout) => ReactNode
  empty?: ReactNode
  /** false: no auto-load on scroll, only the button (the home feed has sections below it). */
  auto?: boolean
  layout?: CardLayout
  /** Show the first item as a featured story above the grid. */
  featureFirst?: boolean
  /** Show "N <noun>" from the API's total above the list. */
  countNoun?: string
}

/** An infinite list: IntersectionObserver loads the next page, with a "Load more" button as the
 * fallback. Items marked "Not interested" disappear immediately. */
export function Feed<T extends ItemSummary>({ queryKey, fetchPage, render, empty, auto = true, layout = 'card', featureFirst, countNoun }: FeedProps<T>) {
  const { profile } = useProfileState()
  const q = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_more && last.page < 1000 ? last.page + 1 : undefined),
  })
  const sentinel = useRef<HTMLDivElement>(null)
  const { hasNextPage, isFetchingNextPage, fetchNextPage, error } = q

  useEffect(() => {
    const el = sentinel.current
    if (!el || !hasNextPage || !auto) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting && !isFetchingNextPage) fetchNextPage()
      },
      { rootMargin: '600px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, auto])

  if (q.isPending) return layout === 'row' ? <RowSkeleton /> : <CardSkeleton />
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />

  const seen = new Set<number>()
  const all = q.data.pages
    .flatMap((p) => p.items)
    .filter((i) => !seen.has(i.id) && seen.add(i.id) && !profile.dismissedIds.includes(i.id))
  if (!all.length) return <EmptyState>{empty ?? 'Nothing here yet. Try removing a filter.'}</EmptyState>
  const [lead, ...restItems] = all
  const items = featureFirst ? restItems : all
  const one = (i: T) => (render ? render(i, layout) : <ItemCard item={i} layout={layout} />)
  const total = q.data.pages[0]?.total ?? 0

  return (
    <div>
      {countNoun && (
        <p className="mb-3 text-xs text-muted-foreground" aria-live="polite">
          {total.toLocaleString()} {countNoun}
        </p>
      )}
      {featureFirst && lead && (
        <div className="mb-4">
          <FeaturedCard item={lead} label="#1 right now" />
        </div>
      )}
      {layout === 'row' ? (
        <ul className="space-y-3">
          {items.map((i) => (
            <li key={i.id} className="min-w-0">
              {one(i)}
            </li>
          ))}
        </ul>
      ) : (
        <CardGrid>
          {items.map((i) => (
            <div key={i.id} className="min-w-0">
              {one(i)}
            </div>
          ))}
        </CardGrid>
      )}
      <div ref={sentinel} className="flex justify-center py-6">
        {q.isFetchNextPageError ? (
          <ErrorState error={error} retry={() => fetchNextPage()} />
        ) : hasNextPage ? (
          <Button variant="outline" disabled={isFetchingNextPage} onClick={() => fetchNextPage()}>
            {isFetchingNextPage ? 'Loading…' : 'Load more'}
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">You're all caught up.</p>
        )}
      </div>
    </div>
  )
}
