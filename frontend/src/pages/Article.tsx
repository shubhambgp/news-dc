import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Bookmark, BookmarkCheck, EyeOff, MessageSquare } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { ItemCard } from '@/components/ItemCard'
import { EmptyState, ErrorState, ListSkeleton, Quality, TypeBadge } from '@/components/common'
import { Button } from '@/components/ui/button'
import { ApiError, api, type ItemDetail } from '@/lib/api'
import { fmtDate, safeUrl, timeAgo, useCategories, useTitle } from '@/lib/format'
import { profileStore, useProfileState } from '@/lib/profile'

const READ_AFTER_MS = 30_000

type Discussion = { type?: string; url?: string; title?: string; points?: number; comments?: number }

/** Reading tracking: opening counts +1 once per visit, staying 30 s (tab visible) counts +2. */
function useReadingTracker(item: ItemDetail | undefined) {
  const opened = useRef<number | null>(null) // StrictMode runs effects twice; count one open
  useEffect(() => {
    if (!item) return
    if (opened.current !== item.id) profileStore.track('open', item)
    opened.current = item.id
    let visibleMs = 0
    let last = Date.now()
    const tick = setInterval(() => {
      const now = Date.now()
      if (document.visibilityState === 'visible') visibleMs += now - last
      last = now
      if (visibleMs >= READ_AFTER_MS) {
        profileStore.track('read', item)
        clearInterval(tick)
      }
    }, 1000)
    return () => clearInterval(tick)
  }, [item])
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">{title}</h2>
      {children}
    </section>
  )
}

export default function ArticlePage() {
  const id = Number(useParams().id)
  const valid = Number.isSafeInteger(id) && id > 0
  const navigate = useNavigate()
  const { name } = useCategories()
  const { profile } = useProfileState()
  const q = useQuery({ queryKey: ['item', id], queryFn: () => api.item(id), enabled: valid })
  const related = useQuery({ queryKey: ['related', id], queryFn: () => api.related(id), enabled: valid })
  const item = q.data
  useTitle(item?.title ?? 'Article', item?.summary ?? undefined)
  useReadingTracker(item)

  if (!valid || (q.error instanceof ApiError && q.error.status === 404))
    return (
      <EmptyState>
        This article isn't available. <Link to="/" className="text-primary underline">Back to the feed</Link>
      </EmptyState>
    )
  if (q.isPending) return <ListSkeleton rows={4} />
  if (q.isError || !item) return <ErrorState error={q.error} retry={() => q.refetch()} />

  const saved = profile.bookmarkIds.includes(item.id)
  const original = safeUrl(item.url)
  const discussions = (item.related_links as Discussion[]).filter((l) => l?.type === 'hn_discussion' && safeUrl(l.url))
  const pdf = (item.related_links as Discussion[]).find((l) => l?.type === 'pdf' && safeUrl(l.url))
  const hn = safeUrl(item.discussion_url)
  const ents = Object.entries(item.entities).filter(([, v]) => v.length) as [string, string[]][]

  return (
    <article data-card-page className="mx-auto max-w-3xl">
      <nav aria-label="Breadcrumb" className="mb-2 text-xs text-muted-foreground">
        <Link to="/" className="hover:underline">Home</Link>
        {item.primary_category && (
          <>
            {' / '}
            <Link to={`/topics/${item.primary_category}`} className="hover:underline">
              {name(item.primary_category)}
            </Link>
          </>
        )}
      </nav>
      <h1 className="text-2xl leading-tight font-semibold tracking-tight">{item.title}</h1>
      <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        <span>{item.publisher}</span>
        {item.author && <span>by {item.author}</span>}
        <span aria-hidden>·</span>
        <time dateTime={item.published_at ?? undefined} title={fmtDate(item.published_at)}>
          {fmtDate(item.published_at)} ({timeAgo(item.published_at)})
        </time>
        {item.source && <span>via {item.source.name}</span>}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <TypeBadge type={item.content_type} />
        {item.categories.map((c) => (
          <Link key={c} to={`/topics/${c}`} className="rounded-full border px-2 py-0.5 text-xs hover:bg-accent">
            {name(c)}
          </Link>
        ))}
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Quality score={item.quality_score} /> Quality {item.quality_score ?? '–'} · Relevance {item.relevance_score ?? '–'}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {original && (
          <Button asChild>
            <a data-original href={original} target="_blank" rel="noopener noreferrer">
              Read original <ArrowUpRight />
            </a>
          </Button>
        )}
        <Button data-bookmark variant="outline" aria-pressed={saved} onClick={() => profileStore.toggleBookmark(item)}>
          {saved ? <BookmarkCheck /> : <Bookmark />} {saved ? 'Bookmarked' : 'Bookmark'}
        </Button>
        <Button
          data-dismiss
          variant="ghost"
          onClick={() => {
            profileStore.track('dismiss', item)
            navigate(-1)
          }}
        >
          <EyeOff /> Not interested
        </Button>
      </div>

      {item.summary && (
        <Section title="AI summary">
          <p className="leading-relaxed">{item.summary}</p>
          <p className="mt-1 text-xs text-muted-foreground">Written by NewsDC's AI from the source. Check the original for details.</p>
        </Section>
      )}

      {item.key_insights.length > 0 && (
        <Section title="Key insights">
          <ul className="space-y-2">
            {item.key_insights.map((k, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <span
                  className={
                    k.type === 'technical'
                      ? 'h-fit shrink-0 rounded bg-violet-100 px-1.5 py-0.5 text-[11px] font-medium text-violet-900 dark:bg-violet-950 dark:text-violet-200'
                      : 'h-fit shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200'
                  }
                >
                  {k.type === 'technical' ? 'Technical' : 'Business'}
                </span>
                {k.text}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(ents.length > 0 || item.tags.length > 0) && (
        <Section title="Entities and tags">
          <dl className="space-y-1 text-sm">
            {ents.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="w-28 shrink-0 text-muted-foreground capitalize">{k}</dt>
                <dd>{v.join(', ')}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 flex flex-wrap gap-1">
            {item.tags.map((t) => (
              <Link key={t} to={`/search?q=${encodeURIComponent(t)}`} className="rounded bg-muted px-1.5 py-0.5 text-xs hover:bg-accent">
                #{t}
              </Link>
            ))}
          </p>
        </Section>
      )}

      {(hn || discussions.length > 0 || pdf) && (
        <Section title="Discussion">
          <ul className="space-y-1 text-sm">
            {hn && (
              <li>
                <a href={hn} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                  <MessageSquare className="size-4" aria-hidden /> Hacker News discussion
                  {item.comments_count != null && ` (${item.comments_count} comments, ${item.points ?? 0} points)`}
                </a>
              </li>
            )}
            {discussions
              .filter((d) => d.url !== item.discussion_url)
              .map((d) => (
                <li key={d.url}>
                  <a href={safeUrl(d.url)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                    <MessageSquare className="size-4" aria-hidden /> HN: {d.title ?? 'discussion'} ({d.comments ?? 0} comments)
                  </a>
                </li>
              ))}
            {pdf && (
              <li>
                <a href={safeUrl(pdf.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  PDF
                </a>
              </li>
            )}
          </ul>
        </Section>
      )}

      {(item.coverage.length > 1 || item.also_covered_by.length > 0) && (
        <Section title="Also covered by">
          <ul className="space-y-1 text-sm">
            {item.coverage
              .filter((c) => !c.is_primary)
              .map((c) => (
                <li key={c.source.key + c.url}>
                  <a href={safeUrl(c.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    {c.source.name}
                  </a>
                  <span className="text-muted-foreground"> · {timeAgo(c.published_at ?? c.first_seen_at)}</span>
                </li>
              ))}
            {item.also_covered_by.map((d) => (
              <li key={d.id}>
                <a href={safeUrl(d.url)} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  {d.title}
                </a>
                <span className="text-muted-foreground"> · {d.publisher} · {timeAgo(d.published_at)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Related articles">
        {related.isPending ? (
          <ListSkeleton rows={3} />
        ) : related.isError ? (
          <ErrorState error={related.error} retry={() => related.refetch()} />
        ) : related.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No related articles yet.</p>
        ) : (
          <div className="divide-y">
            {related.data.map((r) => (
              <ItemCard key={r.id} item={r} dismissible={false} />
            ))}
          </div>
        )}
      </Section>
    </article>
  )
}
