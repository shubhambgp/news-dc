import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useRef, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { CardGrid, CardSkeleton, EmptyState, ErrorState } from '@/components/common'
import { ItemCard } from '@/components/ItemCard'
import { Button } from '@/components/ui/button'
import { CONTENT_TYPES, type ItemSummary, type Page } from '@/lib/api'
import { useCategories, useSources } from '@/lib/format'
import { useProfileState } from '@/lib/profile'

const selectCls =
  'h-9 min-w-0 rounded-lg border bg-card px-2.5 text-sm shadow-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'

export function Filters({ hideCategory, children }: { hideCategory?: boolean; children?: ReactNode }) {
  const [sp, setSp] = useSearchParams()
  const { topics } = useCategories()
  const sources = useSources()
  const set = (k: string, v: string) =>
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (v) next.set(k, v)
        else next.delete(k)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  return (
    <form role="search" aria-label="Filters" className="mb-3 grid grid-cols-2 items-center gap-2 sm:flex sm:flex-wrap" onSubmit={(e) => e.preventDefault()}>
      {!hideCategory && (
        <select aria-label="Category" className={selectCls} value={sp.get('category') ?? ''} onChange={(e) => set('category', e.target.value)}>
          <option value="">All categories</option>
          {topics.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.name}
            </option>
          ))}
        </select>
      )}
      <select aria-label="Content type" className={selectCls} value={sp.get('content_type') ?? ''} onChange={(e) => set('content_type', e.target.value)}>
        <option value="">All types</option>
        {CONTENT_TYPES.map((t) => (
          <option key={t} value={t}>
            {t[0].toUpperCase() + t.slice(1)}
          </option>
        ))}
      </select>
      <select aria-label="Source" className={selectCls} value={sp.get('source') ?? ''} onChange={(e) => set('source', e.target.value)}>
        <option value="">All sources</option>
        {sources.map((s) => (
          <option key={s.key} value={s.key}>
            {s.name}
          </option>
        ))}
      </select>
      <select aria-label="Minimum quality" className={selectCls} value={sp.get('min_quality') ?? ''} onChange={(e) => set('min_quality', e.target.value)}>
        <option value="">Any quality</option>
        {[40, 60, 70, 80].map((q) => (
          <option key={q} value={q}>
            Quality ≥ {q}
          </option>
        ))}
      </select>
      {children}
    </form>
  )
}

type FeedProps<T extends ItemSummary> = {
  queryKey: unknown[]
  fetchPage: (page: number) => Promise<Page<T>>
  render?: (item: T) => ReactNode
  empty?: ReactNode
  pageSize?: number
}

/** An infinite list: IntersectionObserver loads the next page, with a "Load more" button as the
 * fallback. Items marked "Not interested" disappear immediately. */
export function Feed<T extends ItemSummary>({ queryKey, fetchPage, render, empty }: FeedProps<T>) {
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
    if (!el || !hasNextPage) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting && !isFetchingNextPage) fetchNextPage()
      },
      { rootMargin: '600px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  if (q.isPending) return <CardSkeleton />
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />

  const seen = new Set<number>()
  const items = q.data.pages
    .flatMap((p) => p.items)
    .filter((i) => !seen.has(i.id) && seen.add(i.id) && !profile.dismissedIds.includes(i.id))
  if (!items.length) return <EmptyState>{empty ?? 'Nothing here yet. Try removing a filter.'}</EmptyState>

  return (
    <div>
      <CardGrid>{items.map((i) => <div key={i.id}>{render ? render(i) : <ItemCard item={i} />}</div>)}</CardGrid>
      <div ref={sentinel} className="flex justify-center py-4">
        {q.isFetchNextPageError ? (
          <ErrorState error={error} retry={() => fetchNextPage()} />
        ) : hasNextPage ? (
          <Button variant="outline" size="sm" disabled={isFetchingNextPage} onClick={() => fetchNextPage()}>
            {isFetchingNextPage ? 'Loading…' : 'Load more'}
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">You're all caught up.</p>
        )}
      </div>
    </div>
  )
}
