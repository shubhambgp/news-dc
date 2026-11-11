import { useQuery } from '@tanstack/react-query'
import { Flame, Layers, Star } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'

import { Feed, Filters, ViewToggle } from '@/components/Feed'
import { Segmented } from '@/components/ui/segmented'
import { useFilterParams, useView } from '@/lib/filters'
import { CardGrid, CardSkeleton, Cover, EmptyState, ErrorState, PageHeader } from '@/components/common'
import { categoryLook } from '@/lib/category'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { timeAgo, useCategories, useTitle } from '@/lib/format'

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
  const [view] = useView()
  const w = (sp.get('window') as Window) in WINDOWS ? (sp.get('window') as Window) : '7d'
  const from = since(w)
  const setWindow = (k: Window) =>
    setSp(
      (p) => {
        const n = new URLSearchParams(p)
        n.set('window', k)
        return n
      },
      { replace: true },
    )
  return (
    <>
      <PageHeader title="Trending" icon={Flame} description="Engagement (points, comments), quality and how many outlets covered a story, fading with age.">
        <Segmented label="Time window" value={w} onChange={setWindow} options={(Object.keys(WINDOWS) as Window[]).map((k) => [k, k] as const)} />
      </PageHeader>
      <Filters toolbar={<ViewToggle />} />
      <Feed
        queryKey={['trending', filters, from]}
        fetchPage={(page) => api.trending({ ...filters, from, page })}
        layout={view}
        featureFirst={view === 'card'}
        countNoun={`articles in the last ${w}`}
      />
    </>
  )
}

export function RelevantPage() {
  useTitle('Most relevant', 'The most relevant, highest-quality data center stories.')
  const filters = useFilterParams()
  const [view] = useView()
  return (
    <>
      <PageHeader title="Most relevant" icon={Star} description="Ranked by the AI relevance and quality scores, with a gentle preference for newer stories." />
      <Filters toolbar={<ViewToggle />} />
      <Feed queryKey={['relevant', filters]} fetchPage={(page) => api.relevant({ ...filters, page })} layout={view} countNoun="articles" />
    </>
  )
}

/** Activity from the topic's newest item (real data; `/topics` has no per-topic trend). */
function activity(latest: string | null | undefined): { label: string; cls: string } {
  const h = latest ? (Date.now() - new Date(latest).getTime()) / 3_600_000 : Infinity
  if (h < 24) return { label: 'Active today', cls: 'bg-success/12 text-success-ink' }
  if (h < 24 * 7) return { label: 'This week', cls: 'bg-primary/12 text-primary-ink' }
  return { label: 'Quiet', cls: 'bg-elevated text-muted-foreground' }
}

export function TopicsPage() {
  useTitle('Topics', 'The 14 data center categories NewsDC follows.')
  const { query } = useCategories()
  if (query.isPending)
    return (
      <>
        <PageHeader title="Topics" icon={Layers} description="The 14 data center categories NewsDC follows. Every article has one primary category and can carry a few more." />
        <CardSkeleton count={8} />
      </>
    )
  if (query.isError) return <ErrorState error={query.error} retry={() => query.refetch()} />
  const max = Math.max(1, ...query.data.map((t) => t.item_count))
  const total = query.data.reduce((n, t) => n + t.item_count, 0)
  return (
    <>
      <PageHeader title="Topics" icon={Layers} description="The 14 data center categories NewsDC follows. Every article has one primary category and can carry a few more." />
      <CardGrid>
        {query.data.map((t) => {
          const act = activity(t.latest[0]?.published_at)
          const share = total ? Math.round((t.item_count / total) * 100) : 0
          return (
            <article key={t.slug} className="group relative flex flex-col overflow-hidden rounded-xl border bg-surface shadow-card transition hover:border-primary/40 hover:shadow-raised has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring">
              <Cover slug={t.slug} className="flex h-24 items-end gap-2 p-4" iconClass="size-20">
                <h2 className="relative z-10 min-w-0 flex-1 text-lg leading-tight font-semibold text-white">
                  <Link to={`/topics/${t.slug}`} className="after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
                    {t.name}
                  </Link>
                </h2>
              </Cover>
              <div className="flex flex-1 flex-col p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className={cn('rounded-md px-1.5 py-0.5 text-2xs font-medium', act.cls)}>{act.label}</span>
                  {t.latest[0] && <span className="text-muted-foreground">Updated {timeAgo(t.latest[0].published_at)}</span>}
                </div>
                <p className="line-clamp-2 text-sm text-muted-foreground">{t.description}</p>
                <div className="mt-3">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium tabular-nums">{t.item_count.toLocaleString()} articles</span>
                    <span className="text-muted-foreground tabular-nums">{share}% of topic labels</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-elevated" aria-hidden>
                    <div className="h-full rounded-full bg-primary" style={{ width: `${(t.item_count / max) * 100}%` }} />
                  </div>
                </div>
                {t.latest.length > 0 && (
                  <ul className="relative z-10 mt-3 space-y-2 border-t pt-3 text-sm">
                    {t.latest.map((i) => (
                      <li key={i.id} className="leading-snug">
                        <Link to={`/article/${i.id}`} className="line-clamp-2 py-1 hover:text-primary-ink hover:underline">
                          {i.title}
                        </Link>
                        <span className="text-xs text-muted-foreground">
                          {i.publisher ?? i.source?.name} · {timeAgo(i.published_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </article>
          )
        })}
      </CardGrid>
    </>
  )
}

const SORTS = [
  ['latest', 'Latest'],
  ['trending', 'Trending'],
  ['relevant', 'Relevant'],
  ['quality', 'Quality'],
] as const
type Sort = (typeof SORTS)[number][0]

export function TopicPage() {
  const { slug = '' } = useParams()
  const filters = useFilterParams()
  const [sp, setSp] = useSearchParams()
  const [view] = useView()
  const sort = (SORTS.find(([k]) => k === sp.get('sort'))?.[0] ?? 'latest') as Sort
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
  const { Icon } = categoryLook(slug)
  const setSort = (v: Sort) =>
    setSp(
      (p) => {
        const n = new URLSearchParams(p)
        if (v === 'latest') n.delete('sort')
        else n.set('sort', v)
        return n
      },
      { replace: true },
    )
  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 text-xs text-muted-foreground">
        <Link to="/topics" className="inline-block py-1 hover:text-foreground hover:underline">
          Topics
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{head.data?.name ?? '…'}</span>
      </nav>
      <Cover slug={slug} className="mb-5 rounded-2xl p-5 sm:p-6" iconClass="size-40 -right-6 -bottom-8">
        <div className="relative z-10 flex items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-white/15 text-white backdrop-blur-sm" aria-hidden>
            <Icon className="size-6" />
          </span>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{head.data?.name ?? <span className="opacity-0">…</span>}</h1>
            <p className="mt-1 line-clamp-2 min-h-10 max-w-[72ch] text-sm text-white/85">{head.data?.description ?? '\u00a0'}</p>
            <p className="mt-2 text-xs font-medium text-white/85">{head.data ? `${head.data.items.total.toLocaleString()} articles` : '\u00a0'}</p>
          </div>
        </div>
      </Cover>
      <Filters
        hideCategory
        toolbar={
          <>
            <Segmented label="Sort" value={sort} onChange={setSort} options={SORTS} />
            <ViewToggle />
          </>
        }
      />
      <Feed
        queryKey={['topic', slug, filters, sort]}
        fetchPage={(page) => api.topic(slug, { ...filters, category: undefined, sort, page }).then((t) => t.items)}
        layout={view}
      />
    </>
  )
}
