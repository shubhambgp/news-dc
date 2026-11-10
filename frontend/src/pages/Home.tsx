import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Check, Compass, Flame, Layers, Newspaper, RotateCcw, Sparkles, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Feed } from '@/components/Feed'
import { ItemCard } from '@/components/ItemCard'
import { Cover, PageHeader, Skeleton } from '@/components/common'
import { categoryLook } from '@/lib/category'
import { Button } from '@/components/ui/button'
import { api, type ForYouItem } from '@/lib/api'
import { timeAgo, useCategories, useTitle } from '@/lib/format'
import { profileStore, toRequest, useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

function TopicPicker() {
  const { topics, query } = useCategories()
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]))
  return (
    <section aria-labelledby="pick-title" className="mb-6 rounded-lg border bg-card p-4">
      <h2 id="pick-title" className="font-semibold">
        What do you want to follow?
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Pick a few topics. Your choices and reading history stay in this browser; there is no account.
      </p>
      {query.isPending ? (
        <Skeleton className="h-20" />
      ) : (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Topics">
          {topics.map((t) => {
            const on = picked.includes(t.slug)
            return (
              <button
                key={t.slug}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(t.slug)}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                  on ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-accent',
                )}
              >
                {on && <Check className="size-3.5" aria-hidden />}
                {t.name}
              </button>
            )
          })}
        </div>
      )}
      <div className="mt-4 flex gap-2">
        <Button size="sm" disabled={!picked.length} onClick={() => profileStore.setTopics(picked)}>
          Show my feed{picked.length ? ` (${picked.length})` : ''}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => profileStore.setTopics([])}>
          Skip
        </Button>
      </div>
    </section>
  )
}

/** Headline and live numbers from `/stats`. Tiles hide if stats fail; the feed still works. */
function Hero() {
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
        [Activity, change == null ? last7.toLocaleString() : `${change > 0 ? '+' : ''}${change}%`, change == null ? 'Last 7 days' : '7-day activity'],
        [Sparkles, `$${s.ai_cost.total_usd.toFixed(2)}`, 'AI cost'],
      ]
    : []
  return (
    <section aria-labelledby="hero-title" className="hero-glow mb-6 rounded-2xl border bg-card/60 p-5 sm:p-6">
      <p id="hero-title" className="text-2xl leading-tight font-bold tracking-tight sm:text-3xl">
        Your AI-powered <span className="text-brand">Data Center Intelligence.</span>
      </p>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        News, research and engineering on infrastructure, AI compute, power, cooling and sustainability, filtered and summarized by AI.
      </p>
      {stats.isPending ? (
        <Skeleton className="mt-4 h-[8.25rem] sm:h-16" />
      ) : (
        tiles.length > 0 && (
          <ul aria-label="NewsDC in numbers" className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {tiles.map(([Icon, value, label]) => (
              <li key={label} className="flex items-center gap-3 rounded-xl border bg-background/60 p-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary" aria-hidden>
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-base leading-tight font-semibold tabular-nums">{value}</span>
                  <span className="block truncate text-xs text-muted-foreground">{label}</span>
                </span>
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  )
}

/** The weekly trend brief (Phase 7) as a banner; hidden when there is none. */
function Briefing() {
  const q = useQuery({ queryKey: ['trends'], queryFn: api.trends, staleTime: 10 * 60_000 })
  const brief = q.data?.brief
  if (!brief) return null
  return (
    <Link
      to="/dashboard"
      className="group mb-6 flex items-center gap-4 rounded-2xl border border-primary/30 bg-primary/8 p-4 hover:border-primary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <span className="bg-brand grid size-11 shrink-0 place-items-center rounded-xl text-white" aria-hidden>
        <Sparkles className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">AI weekly briefing</span>
        <span className="block truncate text-sm text-muted-foreground">
          Top moves and rising topics, written {timeAgo(brief.created_at)} from {brief.sources.length} sources.
        </span>
      </span>
      <span className="bg-brand hidden shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-white sm:inline-flex">
        View briefing <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" aria-hidden />
      </span>
    </Link>
  )
}

/** #1 trending as a featured card, the rest as a horizontal strip. */
function TrendingStrip() {
  const q = useQuery({ queryKey: ['trending-strip'], queryFn: () => api.trending({ page_size: 9 }) })
  const { name } = useCategories()
  if (q.isError) return null
  const [top, ...rest] = q.data?.items ?? []
  return (
    <section aria-labelledby="strip-title" className="mb-6">
      {q.isPending ? (
        <Skeleton className="mb-6 h-80 rounded-2xl md:h-48" />
      ) : (
        top && (
          <article className="group relative mb-6 grid overflow-hidden rounded-2xl border bg-card transition hover:border-primary/40 md:grid-cols-[2fr_3fr]">
            <Cover slug={top.primary_category} className="min-h-36" iconClass="size-36 -right-4 -bottom-6">
              <span className="bg-brand absolute top-3 left-3 z-10 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-white">
                <Flame className="size-3" aria-hidden /> Top story
              </span>
            </Cover>
            <div className="flex flex-col justify-center p-5">
              {top.primary_category && <p className="text-xs font-medium text-primary">{name(top.primary_category)}</p>}
              <h2 className="mt-1 text-lg leading-snug font-bold sm:text-xl">
                <Link to={`/article/${top.id}`} className="after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
                  {top.title}
                </Link>
              </h2>
              {top.summary && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{top.summary}</p>}
              <p className="mt-3 text-xs text-muted-foreground">
                {top.publisher ?? top.source?.name} · {timeAgo(top.published_at)}
              </p>
            </div>
          </article>
        )
      )}
      <h2 id="strip-title" className="mb-3 flex items-center gap-1.5 font-semibold">
        <Flame className="size-4 text-orange-500" aria-hidden /> Trending now
        <Link to="/trending" className="ml-auto inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline">
          See all <ArrowRight className="size-3" aria-hidden />
        </Link>
      </h2>
      <ol className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2">
        {q.isPending
          ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-44 w-60 shrink-0 rounded-xl" />)
          : rest.map((i, n) => (
              <li key={i.id} className="relative w-60 shrink-0 snap-start overflow-hidden rounded-xl border bg-card transition hover:border-primary/40">
                <Cover slug={i.primary_category} className="h-20" iconClass="size-14">
                  <span className="absolute top-2 left-2 z-10 grid size-6 place-items-center rounded-md bg-black/45 text-xs font-bold text-white">{n + 2}</span>
                </Cover>
                <div className="p-3">
                  <Link to={`/article/${i.id}`} className="line-clamp-2 text-sm leading-snug font-semibold after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
                    {i.title}
                  </Link>
                  <p className="mt-1.5 truncate text-xs text-muted-foreground">
                    {i.publisher ?? i.source?.name} · {timeAgo(i.published_at)}
                  </p>
                </div>
              </li>
            ))}
      </ol>
    </section>
  )
}

function ExploreTopics() {
  const { topics } = useCategories()
  if (!topics.length) return null
  return (
    <section aria-labelledby="explore-title" className="mb-6">
      <h2 id="explore-title" className="mb-3 flex items-center gap-1.5 font-semibold">
        <Layers className="size-4 text-primary" aria-hidden /> Explore topics
        <Link to="/topics" className="ml-auto inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline">
          All topics <ArrowRight className="size-3" aria-hidden />
        </Link>
      </h2>
      <ul className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-2">
        {topics.map((t) => {
          const { Icon, style } = categoryLook(t.slug)
          return (
            <li key={t.slug} className="shrink-0">
              <Link
                to={`/topics/${t.slug}`}
                style={style}
                className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-sm whitespace-nowrap hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Icon className="size-4 text-[oklch(0.62_0.15_var(--h))]" aria-hidden />
                {t.name}
              </Link>
            </li>
          )
        })}
      </ul>
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
    <section aria-labelledby="int-title" className="rounded-lg border bg-card p-4">
      <h2 id="int-title" className="mb-2 text-sm font-semibold">
        Your interests
      </h2>
      {top.length === 0 && !profile.explicitTopics.length ? (
        <p className="text-xs text-muted-foreground">Open, read and bookmark articles and this feed learns what you like.</p>
      ) : (
        <>
          {profile.explicitTopics.length > 0 && (
            <p className="mb-2 text-xs text-muted-foreground">Picked: {profile.explicitTopics.map(name).join(', ')}</p>
          )}
          <ul className="space-y-1.5">
            {top.map(([slug, w]) => (
              <li key={slug} className="text-xs">
                <div className="flex justify-between">
                  <span>{name(slug)}</span>
                  <span className="text-muted-foreground tabular-nums">{w.toFixed(1)}</span>
                </div>
                <div className="mt-0.5 h-1.5 rounded bg-muted" aria-hidden>
                  <div className="h-full rounded bg-primary" style={{ width: `${(w / max) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
          {tags.length > 0 && (
            <p className="mt-3 flex flex-wrap gap-1">
              {tags.map(([t]) => (
                <span key={t} className="rounded bg-muted px-1.5 py-0.5 text-[11px]">
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
    <div className="grid gap-6 xl:grid-cols-[1fr_16rem]">
      <div className="min-w-0">
        <h1 className="sr-only">For You</h1>
        <Hero />
        {!profile.onboarded && <TopicPicker />}
        <details className="mb-4 xl:hidden">
          <summary className="cursor-pointer text-sm font-medium">Your interests</summary>
          <div className="mt-2">
            <Interests />
          </div>
        </details>
        <Briefing />
        <TrendingStrip />
        <ExploreTopics />
        <PageHeader title="For You" />
        <Feed<ForYouItem>
          // The read/bookmark lists change while reading; refetch only when preferences change.
          queryKey={['foryou', body.categoryWeights, body.tagWeights, body.explicitTopics, body.dismissedIds.length]}
          fetchPage={(page) => api.forYou(body, { page, page_size: 20 })}
          render={(i) => (
            <ItemCard
              item={i}
              reason={i.reason}
              kicker={
                i.kind === 'discover' && (
                  <span className="bg-brand inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-white">
                    <Compass className="size-3" aria-hidden /> Discover
                  </span>
                )
              }
            />
          )}
        />
      </div>
      <aside className="hidden xl:block" aria-label="Personalization">
        <Interests />
      </aside>
    </div>
  )
}
