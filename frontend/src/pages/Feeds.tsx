import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router'

import { Feed, Filters } from '@/components/Feed'
import { useFilterParams } from '@/lib/filters'
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from '@/components/common'
import { api } from '@/lib/api'
import { timeAgo, useCategories, useTitle } from '@/lib/format'
import { cn } from '@/lib/utils'

const WINDOWS = { '24h': 1, '7d': 7, '30d': 30 } as const
type Window = keyof typeof WINDOWS

/** The window start, rounded to the hour so the query key (and cache) is stable. */
function since(w: Window): string {
  const d = new Date(Date.now() - WINDOWS[w] * 86_400_000)
  d.setUTCMinutes(0, 0, 0)
  return d.toISOString()
}

export function TrendingPage() {
  useTitle('Trending', 'What the data center industry is talking about right now.')
  const filters = useFilterParams()
  const [sp, setSp] = useSearchParams()
  const w = (sp.get('window') as Window) in WINDOWS ? (sp.get('window') as Window) : '7d'
  const from = since(w)
  return (
    <>
      <PageHeader title="Trending">
        <div role="tablist" aria-label="Time window" className="inline-flex rounded-md border p-0.5">
          {(Object.keys(WINDOWS) as Window[]).map((k) => (
            <button
              key={k}
              role="tab"
              aria-selected={k === w}
              onClick={() =>
                setSp(
                  (p) => {
                    const n = new URLSearchParams(p)
                    n.set('window', k)
                    return n
                  },
                  { replace: true },
                )
              }
              className={cn(
                'rounded px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                k === w ? 'bg-primary text-primary-foreground' : 'hover:bg-accent',
              )}
            >
              {k}
            </button>
          ))}
        </div>
      </PageHeader>
      <Filters />
      <Feed queryKey={['trending', filters, from]} fetchPage={(page) => api.trending({ ...filters, from, page })} />
    </>
  )
}

export function RelevantPage() {
  useTitle('Most relevant', 'The most relevant, highest-quality data center stories.')
  const filters = useFilterParams()
  return (
    <>
      <PageHeader title="Most relevant" />
      <Filters />
      <Feed queryKey={['relevant', filters]} fetchPage={(page) => api.relevant({ ...filters, page })} />
    </>
  )
}

export function TopicsPage() {
  useTitle('Topics', 'The 14 data center categories NewsDC follows.')
  const { query } = useCategories()
  if (query.isPending) return <ListSkeleton />
  if (query.isError) return <ErrorState error={query.error} retry={() => query.refetch()} />
  return (
    <>
      <PageHeader title="Topics" />
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {query.data.map((t) => (
          <li key={t.slug} className="flex flex-col rounded-lg border bg-card p-4">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="font-semibold">
                <Link to={`/topics/${t.slug}`} className="hover:underline">
                  {t.name}
                </Link>
              </h2>
              <span className="text-xs text-muted-foreground tabular-nums">{t.item_count} items</span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{t.description}</p>
            <ul className="mt-3 space-y-1.5 text-sm">
              {t.latest.map((i) => (
                <li key={i.id} className="leading-snug">
                  <Link to={`/article/${i.id}`} className="line-clamp-2 hover:underline">
                    {i.title}
                  </Link>
                  <span className="text-xs text-muted-foreground">{timeAgo(i.published_at)}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </>
  )
}

const SORTS = [
  ['latest', 'Latest'],
  ['trending', 'Trending'],
  ['relevant', 'Most relevant'],
  ['quality', 'Quality'],
] as const

export function TopicPage() {
  const { slug = '' } = useParams()
  const filters = useFilterParams()
  const [sp, setSp] = useSearchParams()
  const sort = sp.get('sort') ?? 'latest'
  const head = useQuery({ queryKey: ['topic-head', slug], queryFn: () => api.topic(slug, { page_size: 1 }) })
  useTitle(head.data?.name ?? 'Topic', head.data?.description)
  if (head.isError)
    return head.error && 'status' in head.error && head.error.status === 404 ? (
      <EmptyState>
        This topic doesn't exist. <Link to="/topics" className="text-primary underline">See all topics</Link>
      </EmptyState>
    ) : (
      <ErrorState error={head.error} retry={() => head.refetch()} />
    )
  return (
    <>
      <PageHeader title={head.data?.name ?? '…'} />
      {head.data && <p className="-mt-2 mb-4 text-sm text-muted-foreground">{head.data.description}</p>}
      <Filters hideCategory>
        <select
          aria-label="Sort"
          value={sort}
          onChange={(e) => setSp((p) => {
            const n = new URLSearchParams(p)
            n.set('sort', e.target.value)
            return n
          }, { replace: true })}
          className="h-8 rounded-md border bg-background px-2 text-sm"
        >
          {SORTS.map(([k, l]) => (
            <option key={k} value={k}>
              Sort: {l}
            </option>
          ))}
        </select>
      </Filters>
      <Feed
        queryKey={['topic', slug, filters, sort]}
        fetchPage={(page) => api.topic(slug, { ...filters, category: undefined, sort, page }).then((t) => t.items)}
      />
    </>
  )
}
