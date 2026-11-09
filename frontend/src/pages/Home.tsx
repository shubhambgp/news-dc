import { useQuery } from '@tanstack/react-query'
import { Check, Compass, Flame, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Feed } from '@/components/Feed'
import { ItemCard } from '@/components/ItemCard'
import { PageHeader, Skeleton } from '@/components/common'
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

function TrendingStrip() {
  const q = useQuery({ queryKey: ['trending-strip'], queryFn: () => api.trending({ page_size: 8 }) })
  if (q.isError) return null
  return (
    <section aria-labelledby="strip-title" className="mb-5">
      <h2 id="strip-title" className="mb-2 flex items-center gap-1 text-sm font-semibold">
        <Flame className="size-4 text-orange-500" aria-hidden /> Trending now
        <Link to="/trending" className="ml-auto text-xs font-normal text-primary hover:underline">
          See all
        </Link>
      </h2>
      <ol className="flex snap-x gap-3 overflow-x-auto pb-2">
        {q.isPending
          ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-20 w-60 shrink-0" />)
          : q.data.items.map((i, n) => (
              <li key={i.id} className="w-60 shrink-0 snap-start rounded-lg border bg-card p-3">
                <span className="text-xs font-semibold text-muted-foreground">#{n + 1}</span>
                <Link to={`/article/${i.id}`} className="line-clamp-2 text-sm font-medium hover:underline">
                  {i.title}
                </Link>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {i.publisher} · {timeAgo(i.published_at)}
                </p>
              </li>
            ))}
      </ol>
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
        {!profile.onboarded && <TopicPicker />}
        <details className="mb-4 xl:hidden">
          <summary className="cursor-pointer text-sm font-medium">Your interests</summary>
          <div className="mt-2">
            <Interests />
          </div>
        </details>
        <TrendingStrip />
        <PageHeader title="For You" />
        <Feed<ForYouItem>
          // The read/bookmark lists change while reading; refetch only when preferences change.
          queryKey={['foryou', body.categoryWeights, body.tagWeights, body.explicitTopics, body.dismissedIds.length]}
          fetchPage={(page) => api.forYou(body, { page, page_size: 20 })}
          render={(i) => {
            return (
              <div className={cn(i.kind === 'discover' && 'border-l-2 border-primary pl-2')}>
                {i.kind === 'discover' && (
                  <p className="flex items-center gap-1 pt-2 text-[11px] font-semibold tracking-wide text-primary uppercase">
                    <Compass className="size-3" aria-hidden /> Discover
                  </p>
                )}
                <ItemCard item={i} reason={i.reason} />
              </div>
            )
          }}
        />
      </div>
      <aside className="hidden xl:block" aria-label="Personalization">
        <Interests />
      </aside>
    </div>
  )
}
