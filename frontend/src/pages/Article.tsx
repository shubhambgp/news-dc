import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Bookmark, BookmarkCheck, Briefcase, Check, Cpu, EyeOff, FileText, Link2, MessageSquare, Newspaper, Share2, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { ArticleRow } from '@/components/ArticleCards'
import { ItemCard } from '@/components/ItemCard'
import { CardGrid, Cover, EmptyState, ErrorState, Quality, Skeleton, TypeBadge, WithAside } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ApiError, api, type ItemDetail, type KeyInsight, type RelatedItem } from '@/lib/api'
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

function Section({ title, icon: Icon, children, aside }: { title: string; icon?: typeof Newspaper; children: ReactNode; aside?: boolean }) {
  return (
    <section className={aside ? 'rounded-2xl border bg-surface p-4 shadow-card' : 'mt-8'}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
        {Icon && <Icon className="size-4" aria-hidden />}
        {title}
      </h2>
      {children}
    </section>
  )
}

/** Share via the OS sheet where there is one, else copy the link. */
function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false)
  const share = async () => {
    const url = window.location.href
    try {
      if (navigator.share) await navigator.share({ title, url })
      else {
        await navigator.clipboard.writeText(url)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    } catch {
      // the user closed the share sheet, or clipboard access was refused: nothing to do
    }
  }
  return (
    <Button variant="outline" onClick={() => void share()}>
      {copied ? <Check /> : <Share2 />} {copied ? 'Link copied' : 'Share'}
      <span className="sr-only" aria-live="polite">
        {copied ? 'Link copied to the clipboard' : ''}
      </span>
    </Button>
  )
}

function Insights({ items, type }: { items: KeyInsight[]; type: KeyInsight['type'] }) {
  const list = items.filter((k) => k.type === type)
  if (!list.length) return null
  const technical = type === 'technical'
  return (
    <div className="rounded-xl border bg-surface p-4">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        {technical ? <Cpu className="size-4 text-data" aria-hidden /> : <Briefcase className="size-4 text-success" aria-hidden />}
        {technical ? 'Technical insights' : 'Business implications'}
      </h3>
      <ul className="space-y-2 text-sm leading-relaxed">
        {list.map((k, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className={technical ? 'mt-2 size-1.5 shrink-0 rounded-full bg-data' : 'mt-2 size-1.5 shrink-0 rounded-full bg-success'} />
            {k.text}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Related({ q, layout }: { q: ReturnType<typeof useQuery<RelatedItem[]>>; layout: 'grid' | 'list' }) {
  if (q.isPending) return <Skeleton className={layout === 'list' ? 'h-72' : 'h-64'} />
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />
  if (!q.data.length) return <p className="text-sm text-muted-foreground">No related articles yet.</p>
  return layout === 'list' ? (
    <ul className="-mx-2 space-y-0.5">
      {q.data.map((r) => (
        <li key={r.id}>
          <ArticleRow item={r} />
        </li>
      ))}
    </ul>
  ) : (
    <CardGrid>
      {q.data.map((r) => (
        <ItemCard key={r.id} item={r} dismissible={false} />
      ))}
    </CardGrid>
  )
}

function ArticleSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="mx-auto max-w-3xl space-y-4">
      <Skeleton className="h-3 w-40" />
      <Skeleton className="h-44 rounded-2xl sm:h-56" />
      <Skeleton className="h-8 w-5/6" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-36 rounded-xl" />
    </div>
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
  if (q.isPending) return <ArticleSkeleton />
  if (q.isError || !item) return <ErrorState error={q.error} retry={() => q.refetch()} />

  const saved = profile.bookmarkIds.includes(item.id)
  const original = safeUrl(item.url)
  const discussions = (item.related_links as Discussion[]).filter((l) => l?.type === 'hn_discussion' && safeUrl(l.url))
  const pdf = (item.related_links as Discussion[]).find((l) => l?.type === 'pdf' && safeUrl(l.url))
  const hn = safeUrl(item.discussion_url)
  const ents = Object.entries(item.entities).filter(([, v]) => v.length) as [string, string[]][]
  const publisher = item.publisher ?? item.source?.name ?? ''
  const words = item.summary ? item.summary.trim().split(/\s+/).length : 0
  const others = item.coverage.filter((c) => !c.is_primary)

  const entities = (ents.length > 0 || item.tags.length > 0) && (
    <>
      <dl className="space-y-3 text-sm">
        {ents.map(([k, v]) => (
          <div key={k}>
            <dt className="mb-1 text-xs text-muted-foreground capitalize">{k}</dt>
            <dd className="flex flex-wrap gap-1.5">
              {v.map((e) => (
                <Link key={e} to={`/search?q=${encodeURIComponent(e)}`} className="rounded-md border bg-surface px-2 py-0.5 text-xs hover:bg-elevated">
                  {e}
                </Link>
              ))}
            </dd>
          </div>
        ))}
      </dl>
      {item.tags.length > 0 && (
        <p className="mt-3 flex flex-wrap gap-1.5">
          {item.tags.map((t) => (
            <Link key={t} to={`/search?q=${encodeURIComponent(t)}`} className="rounded-md bg-elevated px-1.5 py-0.5 text-xs text-foreground/85 hover:text-foreground">
              #{t}
            </Link>
          ))}
        </p>
      )}
    </>
  )

  return (
    <WithAside
      label="About this article"
      aside={
        <>
          {entities && (
            <Section title="Entities and tags" aside>
              {entities}
            </Section>
          )}
          <Section title="Related articles" aside>
            <Related q={related} layout="list" />
          </Section>
        </>
      }
    >
      <article data-card-page className="mx-auto max-w-3xl">
        <nav aria-label="Breadcrumb" className="mb-3 text-xs text-muted-foreground">
          <Link to="/" className="hover:text-foreground hover:underline">
            Home
          </Link>
          {item.primary_category && (
            <>
              <span aria-hidden> / </span>
              <Link to={`/topics/${item.primary_category}`} className="hover:text-foreground hover:underline">
                {name(item.primary_category)}
              </Link>
            </>
          )}
        </nav>

        <Cover slug={item.primary_category} className="mb-5 h-36 rounded-2xl sm:h-48" iconClass="size-40 -right-4 -bottom-8">
          <div className="relative z-10 flex flex-wrap gap-2 p-4">
            {item.categories.map((c) => (
              <Badge key={c} asChild variant="overlay">
                <Link to={`/topics/${c}`}>{name(c)}</Link>
              </Badge>
            ))}
          </div>
        </Cover>

        <h1 className="text-2xl leading-tight font-bold tracking-tight text-balance sm:text-3xl 3xl:text-4xl">{item.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-elevated text-xs font-semibold text-foreground uppercase">
              {publisher.slice(0, 1)}
            </span>
            <span className="font-medium text-foreground">{publisher}</span>
          </span>
          {item.author && <span>by {item.author}</span>}
          <span aria-hidden>·</span>
          <time dateTime={item.published_at ?? undefined}>
            {fmtDate(item.published_at)} ({timeAgo(item.published_at)})
          </time>
          {item.source && <span>via {item.source.name}</span>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <TypeBadge type={item.content_type} />
          <span className="inline-flex items-center gap-1.5">
            <Quality score={item.quality_score} /> Quality {item.quality_score ?? '–'} · Relevance {item.relevance_score ?? '–'}
          </span>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {original && (
            <Button asChild>
              <a data-original href={original} target="_blank" rel="noopener noreferrer">
                Read original <ArrowUpRight />
              </a>
            </Button>
          )}
          <Button data-bookmark variant="outline" aria-pressed={saved} onClick={() => profileStore.toggleBookmark(item)}>
            {saved ? <BookmarkCheck className="text-primary" /> : <Bookmark />} {saved ? 'Bookmarked' : 'Bookmark'}
          </Button>
          <ShareButton title={item.title} />
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
          <section aria-labelledby="ai-summary" className="ai-block mt-8 rounded-r-xl p-4 sm:p-5">
            <h2 id="ai-summary" className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              <Sparkles className="size-4 text-ai" aria-hidden /> AI summary
              <Badge variant="ai">AI-generated</Badge>
              <span className="text-xs font-normal text-muted-foreground">{words} words</span>
            </h2>
            <p className="mt-2 text-base leading-relaxed">{item.summary}</p>
            <p className="mt-3 text-xs text-muted-foreground">Written by NewsDC's AI from the source. It can contain mistakes: check the original for details.</p>
          </section>
        )}

        {item.key_insights.length > 0 && (
          <section aria-labelledby="takeaways" className="mt-8">
            <h2 id="takeaways" className="mb-3 flex flex-wrap items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
              Key takeaways <Badge variant="ai" className="normal-case">AI-generated</Badge>
            </h2>
            <div className={new Set(item.key_insights.map((k) => k.type)).size > 1 ? 'grid gap-3 md:grid-cols-2' : 'grid gap-3'}>
              <Insights items={item.key_insights} type="technical" />
              <Insights items={item.key_insights} type="business" />
            </div>
          </section>
        )}

        {item.description && (
          <Section title="From the publisher" icon={FileText}>
            <blockquote className="border-l-2 pl-4 text-sm leading-relaxed text-foreground/85">{item.description}</blockquote>
            <p className="mt-2 text-xs text-muted-foreground">The source's own description, as published by {publisher}.</p>
          </Section>
        )}

        {entities && (
          <div className="xl:hidden">
            <Section title="Entities and tags">{entities}</Section>
          </div>
        )}

        <Section title="Sources and coverage" icon={Link2}>
          <ul className="divide-y rounded-xl border bg-surface text-sm">
            {original && (
              <li className="flex flex-wrap items-baseline justify-between gap-2 p-3">
                <a href={original} target="_blank" rel="noopener noreferrer" className="font-medium text-primary-ink hover:underline">
                  {publisher} (original)
                </a>
                <span className="text-xs text-muted-foreground">{timeAgo(item.published_at)}</span>
              </li>
            )}
            {others.map((c) => (
              <li key={c.source.key + c.url} className="flex flex-wrap items-baseline justify-between gap-2 p-3">
                <a href={safeUrl(c.url)} target="_blank" rel="noopener noreferrer" className="text-primary-ink hover:underline">
                  Found by {c.source.name}
                </a>
                <span className="text-xs text-muted-foreground">{timeAgo(c.published_at ?? c.first_seen_at)}</span>
              </li>
            ))}
            {item.also_covered_by.map((d) => (
              <li key={d.id} className="flex flex-wrap items-baseline justify-between gap-2 p-3">
                <a href={safeUrl(d.url)} target="_blank" rel="noopener noreferrer" className="min-w-0 text-primary-ink hover:underline">
                  {d.title}
                </a>
                <span className="text-xs text-muted-foreground">
                  {d.publisher} · {timeAgo(d.published_at)}
                </span>
              </li>
            ))}
            {pdf && (
              <li className="p-3">
                <a href={safeUrl(pdf.url)} target="_blank" rel="noopener noreferrer" className="text-primary-ink hover:underline">
                  PDF version
                </a>
              </li>
            )}
          </ul>
        </Section>

        {(hn || discussions.length > 0) && (
          <Section title="Discussion" icon={MessageSquare}>
            <ul className="space-y-2 text-sm">
              {hn && (
                <li>
                  <a href={hn} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-primary-ink hover:underline">
                    <MessageSquare className="size-4" aria-hidden /> Hacker News discussion
                    {item.comments_count != null && ` (${item.comments_count} comments, ${item.points ?? 0} points)`}
                  </a>
                </li>
              )}
              {discussions
                .filter((d) => d.url !== item.discussion_url)
                .map((d) => (
                  <li key={d.url}>
                    <a href={safeUrl(d.url)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-primary-ink hover:underline">
                      <MessageSquare className="size-4" aria-hidden /> HN: {d.title ?? 'discussion'} ({d.comments ?? 0} comments)
                    </a>
                  </li>
                ))}
            </ul>
          </Section>
        )}

        <div className="xl:hidden">
          <Section title="Related articles" icon={Newspaper}>
            <Related q={related} layout="grid" />
          </Section>
        </div>
      </article>
    </WithAside>
  )
}
