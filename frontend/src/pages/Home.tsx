import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  Check,
  Compass,
  FlaskConical,
  Flame,
  Layers,
  Newspaper,
  RotateCcw,
  Sparkles,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { ArticleRow, FeaturedCard, TrendingRail } from '@/components/ArticleCards'
import { Feed } from '@/components/Feed'
import { ItemCard } from '@/components/ItemCard'
import { SearchBox } from '@/components/SearchBox'
import { Skeleton, WithAside } from '@/components/common'
import { Button } from '@/components/ui/button'
import { api, type ForYouItem } from '@/lib/api'
import { categoryLook } from '@/lib/category'
import { timeAgo, useCategories, useTitle } from '@/lib/format'
import { profileStore, toRequest, useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

function SectionTitle({ id, icon: Icon, iconClass, children, to, linkLabel }: { id: string; icon: LucideIcon; iconClass?: string; children: ReactNode; to?: string; linkLabel?: string }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Icon className={cn('size-4', iconClass ?? 'text-primary')} aria-hidden />
      <h2 id={id} className="text-lg font-semibold tracking-tight">
        {children}
      </h2>
      {to && (
        <Link to={to} className="ml-auto inline-flex items-center gap-0.5 rounded text-xs font-medium text-primary-ink hover:underline">
          {linkLabel} <ArrowRight className="size-3" aria-hidden />
        </Link>
      )}
    </div>
  )
}

/** One-line welcome with live numbers from `/stats`. Tiles hide if stats fail; the feed still works. */
function Welcome() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, staleTime: 5 * 60_000 })
  const { topics } = useCategories()
  const s = stats.data
  const days = s?.per_day ?? []
  const last7 = days.slice(-7).reduce((n, d) => n + d.items, 0)
  const prev7 = days.slice(-14, -7).reduce((n, d) => n + d.items, 0)
  const change = prev7 ? Math.round(((last7 - prev7) / prev7) * 100) : null
  const tiles: [LucideIcon, string, string][] = s?.funnel
    ? [
        [Newspaper, s.funnel.processed.toLocaleString(), 'Articles'],
        [Layers, String(topics.length || 14), 'Topics'],
        [Activity, change == null ? last7.toLocaleString() : `${change > 0 ? '+' : ''}${change}%`, change == null ? 'This week' : 'vs last week'],
        [Sparkles, `$${s.ai_cost.total_usd.toFixed(2)}`, 'AI cost'],
      ]
    : []
  return (
    <section aria-labelledby="welcome-title" className="hero-glow mb-5 flex flex-col gap-4 rounded-2xl border bg-surface/70 p-4 sm:p-5 2xl:flex-row 2xl:items-center 2xl:justify-between">
      <div className="min-w-0">
        <p id="welcome-title" className="text-xl leading-tight font-bold tracking-tight text-balance sm:text-2xl">
          Your AI-powered <span className="text-primary">Data Center Intelligence</span>
        </p>
        <p className="mt-1 text-sm text-muted-foreground">Infrastructure, AI compute, power, cooling and sustainability, filtered and summarized by AI.</p>
      </div>
      {stats.isPending ? (
        <Skeleton className="h-14 2xl:w-[34rem]" />
      ) : (
        tiles.length > 0 && (
          <ul aria-label="NewsDC in numbers" className="-mx-4 flex shrink-0 gap-2 overflow-x-auto px-4 sm:mx-0 sm:grid sm:grid-cols-4 sm:px-0 2xl:w-[34rem]">
            {tiles.map(([Icon, value, label]) => (
              <li key={label} className="flex min-w-36 shrink-0 items-center gap-2.5 rounded-xl border bg-background/60 px-3 py-2.5 sm:min-w-0">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary" aria-hidden>
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[15px] leading-tight font-semibold tabular-nums">{value}</span>
                  <span className="block text-2xs whitespace-nowrap text-muted-foreground">{label}</span>
                </span>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  )
}

/** First visit: one compact row of topic chips (scrolls on small screens). */
function TopicPicker() {
  const { topics, query } = useCategories()
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]))
  return (
    <section aria-labelledby="pick-title" className="mb-6 rounded-2xl border bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-0 basis-full sm:basis-0 sm:flex-1">
          <h2 id="pick-title" className="font-semibold">
            What do you want to follow?
          </h2>
          <p className="text-xs text-muted-foreground">Your choices and reading history stay in this browser; there is no account.</p>
        </div>
        <div className="order-last flex shrink-0 gap-2 sm:order-none">
          <Button size="sm" disabled={!picked.length} onClick={() => profileStore.setTopics(picked)}>
            Show my feed{picked.length ? ` (${picked.length})` : ''}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => profileStore.setTopics([])}>
            Skip
          </Button>
        </div>
      {query.isPending ? (
        <Skeleton className="h-10 basis-full" />
      ) : (
        <div className="-mx-4 flex basis-full gap-2 overflow-x-auto px-4 pb-1 [mask-image:linear-gradient(to_right,black_92%,transparent)]" role="group" aria-label="Topics">
          {topics.map((t) => {
            const on = picked.includes(t.slug)
            const { Icon, style } = categoryLook(t.slug)
            return (
              <button
                key={t.slug}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(t.slug)}
                style={style}
                className={cn(
                  'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                  on ? 'border-primary bg-primary text-primary-foreground' : 'bg-surface hover:bg-elevated',
                )}
              >
                {on ? <Check className="size-3.5" aria-hidden /> : <Icon className="size-3.5 text-[oklch(0.62_0.15_var(--h))]" aria-hidden />}
                {t.name}
              </button>
            )
          })}
        </div>
      )}
      </div>
    </section>
  )
}

/** Markdown brief → one plain-text line for the teaser (rendered as text, never as HTML). */
const teaser = (md: string) =>
  md
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\[\d+\]/g, '')
    .split('\n')
    .map((l) => l.replace(/^[#>*\-\s\d.]+/, '').replace(/[*_`]/g, '').trim())
    .find((l) => l.length > 40) ?? ''

/** The weekly AI brief (Phase 7) when there is one; otherwise this week's rising terms from
 * `/trends` (computed from tags, not AI-written, and labelled so). Hidden if neither exists. */
function Briefing() {
  const q = useQuery({ queryKey: ['trends'], queryFn: api.trends, staleTime: 10 * 60_000 })
  if (q.isPending) return <Skeleton className="mb-6 h-56 rounded-2xl sm:h-52" />
  const brief = q.data?.brief
  if (brief)
    return (
      <Link
        to="/dashboard"
        className="ai-block group mb-6 flex items-start gap-4 rounded-2xl border border-ai/25 p-4 transition-colors hover:border-ai/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none sm:p-5"
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-ai text-ai-foreground" aria-hidden>
          <Sparkles className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold">Weekly AI briefing</span>
            <span className="text-xs text-muted-foreground">
              AI-generated · {brief.sources.length} sources · {timeAgo(brief.created_at)}
            </span>
          </span>
          <span className="mt-1 line-clamp-2 block text-sm text-foreground/85">{teaser(brief.content_md)}</span>
          <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-ai-ink">
            Read the briefing <ArrowRight className="size-3 transition group-hover:translate-x-0.5" aria-hidden />
          </span>
        </span>
      </Link>
    )
  const rising = [...(q.data?.tags ?? []), ...(q.data?.companies ?? [])].sort((a, b) => b.change_pct - a.change_pct).slice(0, 8)
  if (!rising.length) return null
  return (
    <section aria-labelledby="signals-title" className="mb-6 rounded-2xl border bg-surface p-4 shadow-card sm:p-5">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-2">
        <h2 id="signals-title" className="flex items-center gap-2 font-semibold">
          <TrendingUp className="size-4 text-data" aria-hidden /> Rising this week
        </h2>
        <span className="text-xs text-muted-foreground">Tags and companies, last 7 days vs the 4 weeks before. The weekly AI briefing appears here on Mondays.</span>
        <Link to="/dashboard" className="ml-auto inline-flex items-center gap-0.5 text-xs font-medium text-primary-ink hover:underline">
          All signals <ArrowRight className="size-3" aria-hidden />
        </Link>
      </div>
      <ul className="flex flex-wrap gap-2">
        {rising.map((t) => (
          <li key={t.term}>
            <Link
              to={`/search?q=${encodeURIComponent(t.term)}`}
              className="inline-flex items-center gap-1.5 rounded-full border bg-background/60 px-3 py-1 text-sm hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {t.term}
              <span className="text-2xs font-semibold text-success-ink tabular-nums">{t.new ? 'new' : `+${Math.round(t.change_pct)}%`}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** #1 trending as the featured story, the next eight as a numbered rail. */
function Trending() {
  const q = useQuery({ queryKey: ['trending-strip'], queryFn: () => api.trending({ page_size: 9 }) })
  if (q.isError) return null
  const [top, ...rest] = q.data?.items ?? []
  return (
    <>
      <div className="mb-6">{q.isPending ? <Skeleton className="h-96 rounded-2xl md:h-64" /> : top && <FeaturedCard item={top} />}</div>
      <section aria-labelledby="strip-title" className="mb-8">
        <SectionTitle id="strip-title" icon={Flame} iconClass="text-orange-500" to="/trending" linkLabel="See all">
          Trending now
        </SectionTitle>
        {q.isPending ? (
          <div className="flex gap-3 overflow-hidden">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-[10.75rem] w-64 shrink-0 rounded-xl" />
            ))}
          </div>
        ) : (
          <TrendingRail items={rest} start={2} />
        )}
      </section>
    </>
  )
}

function ExploreTopics({ layout }: { layout: 'chips' | 'list' }) {
  const { topics, query } = useCategories()
  if (query.isPending) return <Skeleton className={layout === 'chips' ? 'mb-8 h-20' : 'h-[48rem] rounded-2xl'} />
  if (!topics.length) return null
  const id = `explore-${layout}`
  return (
    <section aria-labelledby={id} className={layout === 'chips' ? 'mb-8' : 'rounded-2xl border bg-surface p-4 shadow-card'}>
      <SectionTitle id={id} icon={Layers} to="/topics" linkLabel="All topics">
        Explore topics
      </SectionTitle>
      {layout === 'chips' ? (
        <ul className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6 lg:mx-0 lg:flex-wrap lg:px-0">
          {topics.map((t) => {
            const { Icon, style } = categoryLook(t.slug)
            return (
              <li key={t.slug} className="shrink-0">
                <Link
                  to={`/topics/${t.slug}`}
                  style={style}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border bg-surface px-3 text-sm whitespace-nowrap hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <Icon className="size-4 text-[oklch(0.62_0.15_var(--h))]" aria-hidden />
                  {t.name}
                  <span className="text-2xs text-muted-foreground tabular-nums">{t.item_count}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      ) : (
        <ul className="-mx-2 space-y-0.5">
          {topics.map((t) => {
            const { Icon, style } = categoryLook(t.slug)
            const latest = t.latest[0]?.published_at
            return (
              <li key={t.slug}>
                <Link
                  to={`/topics/${t.slug}`}
                  style={style}
                  className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <span className="grid size-7 shrink-0 place-items-center rounded-md bg-[oklch(0.62_0.15_var(--h)/0.14)]" aria-hidden>
                    <Icon className="size-4 text-[oklch(0.62_0.15_var(--h))]" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{t.name}</span>
                    {latest && <span className="block text-2xs text-muted-foreground">Updated {timeAgo(latest)}</span>}
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">{t.item_count}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Newest research items (existing `/items?content_type=research`). */
function LatestResearch({ layout }: { layout: 'grid' | 'list' }) {
  const q = useQuery({ queryKey: ['latest-research'], queryFn: () => api.items({ content_type: 'research', page_size: 6 }) })
  if (q.isError) return null
  const id = `research-${layout}`
  const items = q.data?.items.slice(0, layout === 'list' ? 5 : 6) ?? []
  return (
    <section aria-labelledby={id} className={layout === 'grid' ? 'mb-8' : 'rounded-2xl border bg-surface p-4 shadow-card'}>
      <SectionTitle id={id} icon={FlaskConical} iconClass="text-ai" to="/search?q=research&content_type=research&sort=latest" linkLabel="More research">
        Latest research
      </SectionTitle>
      {q.isPending ? (
        <Skeleton className={layout === 'list' ? 'h-[23rem]' : 'h-48'} />
      ) : (
        <ul className={cn('-mx-2', layout === 'grid' ? 'grid gap-1 sm:grid-cols-2' : 'space-y-0.5')}>
          {items.map((i) => (
            <li key={i.id}>
              <ArticleRow item={i} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** "Your interests": the profile's weights, so the personalization is visible, with a reset. */
function Interests() {
  const { profile } = useProfileState()
  const { name } = useCategories()
  const top = Object.entries(profile.categoryWeights)
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
  const max = top[0]?.[1] ?? 1
  const tags = Object.entries(profile.tagWeights)
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
  return (
    <section aria-labelledby="int-title" className="rounded-2xl border bg-surface p-4 shadow-card">
      <h2 id="int-title" className="mb-1 flex items-center gap-2 font-semibold">
        <Sparkles className="size-4 text-ai" aria-hidden /> Your interests
      </h2>
      <p className="mb-3 text-xs text-muted-foreground">Learned in this browser from what you open, read and save.</p>
      {top.length === 0 && !profile.explicitTopics.length ? (
        <p className="rounded-lg bg-elevated p-3 text-xs text-muted-foreground">Nothing yet. Open, read and bookmark articles and For You adapts.</p>
      ) : (
        <>
          {profile.explicitTopics.length > 0 && <p className="mb-2 text-xs text-muted-foreground">Following: {profile.explicitTopics.map(name).join(', ')}</p>}
          <ul className="space-y-2">
            {top.map(([slug, w]) => (
              <li key={slug} className="text-xs">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{name(slug)}</span>
                  <span className="text-muted-foreground tabular-nums">{w.toFixed(1)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-elevated" aria-hidden>
                  <div className="h-full rounded-full bg-primary" style={{ width: `${(w / max) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
          {tags.length > 0 && (
            <p className="mt-3 flex flex-wrap gap-1">
              {tags.map(([t]) => (
                <span key={t} className="rounded-md bg-elevated px-1.5 py-0.5 text-2xs">
                  {t}
                </span>
              ))}
            </p>
          )}
        </>
      )}
      <Button variant="outline" size="sm" className="mt-3 w-full" onClick={() => profileStore.reset()}>
        <RotateCcw /> Reset my preferences
      </Button>
    </section>
  )
}

export default function HomePage() {
  useTitle('', 'Data center news, research and engineering, filtered and summarized by AI.')
  const { profile } = useProfileState()
  const { topics } = useCategories()
  const known = topics.length ? new Set(topics.map((t) => t.slug)) : undefined
  const body = toRequest(profile, known)

  return (
    <WithAside
      label="Personalization and topics"
      aside={
        <>
          <Interests />
          <ExploreTopics layout="list" />
          <LatestResearch layout="list" />
        </>
      }
    >
      <h1 className="sr-only">For You</h1>
      <Welcome />
      <SearchBox id="home-search" large className="mb-5 md:hidden" />
      {!profile.onboarded && <TopicPicker />}
      <Trending />
      <Briefing />

      <section aria-labelledby="foryou-title" className="relative mb-8">
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <Sparkles className="size-4 text-ai" aria-hidden />
          <h2 id="foryou-title" className="text-lg font-semibold tracking-tight">
            For You
          </h2>
          <span className="text-xs text-muted-foreground">Ranked from your interests, plus a few discoveries</span>
          <details className="group ml-auto xl:hidden">
            <summary className="cursor-pointer list-none rounded-full border bg-surface px-3 py-1 text-xs font-medium hover:bg-elevated">Your interests</summary>
            <div className="absolute right-0 left-0 z-20 mt-2 sm:left-auto sm:w-80">
              <Interests />
            </div>
          </details>
        </div>
        <Feed<ForYouItem>
          auto={false}
          // The read/bookmark lists change while reading; refetch only when preferences change.
          queryKey={['foryou', body.categoryWeights, body.tagWeights, body.explicitTopics, body.dismissedIds.length]}
          fetchPage={(page) => api.forYou(body, { page, page_size: 12 })}
          render={(i) => (
            <ItemCard
              item={i}
              reason={i.reason}
              kicker={
                i.kind === 'discover' && (
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-ai px-2.5 py-0.5 text-2xs font-semibold text-ai-foreground">
                    <Compass className="size-3" aria-hidden /> Discover
                  </span>
                )
              }
            />
          )}
        />
      </section>

      <div className="xl:hidden">
        <ExploreTopics layout="chips" />
        <LatestResearch layout="grid" />
      </div>
    </WithAside>
  )
}
