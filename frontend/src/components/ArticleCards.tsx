import { Flame } from 'lucide-react'
import { Link } from 'react-router'

import { Cover, TypeBadge } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import type { ItemSummary } from '@/lib/api'
import { categoryLook } from '@/lib/category'
import { timeAgo, useCategories } from '@/lib/format'

// Article presentations besides the standard feed card (`ItemCard`). Each one links the whole
// block through its title (`after:inset-0`), so there is one tab stop per article.

const source = (i: ItemSummary) => i.publisher ?? i.source?.name ?? ''

/** The lead story: artwork beside (≥ 768 px) or above the headline. */
export function FeaturedCard({ item, label = 'Top story' }: { item: ItemSummary; label?: string }) {
  const { name } = useCategories()
  return (
    <article className="group relative grid overflow-hidden rounded-2xl border bg-surface shadow-card transition hover:border-primary/40 hover:shadow-raised md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <Cover slug={item.primary_category} className="min-h-40 md:min-h-56" iconClass="size-36 -right-4 -bottom-6">
        <Badge className="absolute top-3 left-3 z-10 rounded-full bg-primary px-2.5 text-primary-foreground">
          <Flame aria-hidden /> {label}
        </Badge>
      </Cover>
      <div className="flex flex-col justify-center gap-2 p-5 md:p-6">
        {item.primary_category && <p className="text-xs font-semibold text-primary-ink">{name(item.primary_category)}</p>}
        <h2 className="line-clamp-3 text-xl leading-snug font-bold tracking-tight text-balance md:text-2xl">
          <Link to={`/article/${item.id}`} className="after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
            {item.title}
          </Link>
        </h2>
        {item.summary && <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground md:text-[15px]">{item.summary}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/85">{source(item)}</span>
          <span aria-hidden>·</span>
          <time dateTime={item.published_at ?? undefined}>{timeAgo(item.published_at)}</time>
          <TypeBadge type={item.content_type} />
        </p>
      </div>
    </article>
  )
}

/** A compact row: small artwork tile, two-line title, source and time. */
export function ArticleRow({ item, rank }: { item: ItemSummary; rank?: number }) {
  const { Icon, style } = categoryLook(item.primary_category)
  return (
    <article className="group relative flex items-start gap-3 rounded-lg p-2 transition-colors hover:bg-elevated">
      <span className="cover relative grid size-12 shrink-0 place-items-center overflow-hidden rounded-lg" style={style} aria-hidden>
        {rank != null ? <span className="text-sm font-bold text-white">{rank}</span> : <Icon className="size-5 text-white/85" />}
      </span>
      <div className="min-w-0">
        <h3 className="line-clamp-2 text-sm leading-snug font-medium">
          <Link to={`/article/${item.id}`} className="after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
            {item.title}
          </Link>
        </h3>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {source(item)} · {timeAgo(item.published_at)}
        </p>
      </div>
    </article>
  )
}

/** Horizontally scrolling numbered cards (Trending now). `start` is the first rank shown. */
export function TrendingRail({ items, start = 1 }: { items: ItemSummary[]; start?: number }) {
  return (
    <ol className="-mx-4 flex snap-x scroll-px-4 gap-3 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:scroll-px-6 sm:px-6 lg:mx-0 lg:scroll-px-0 lg:px-0">
      {items.map((i, n) => (
        <li key={i.id} className="relative w-64 shrink-0 snap-start overflow-hidden rounded-xl border bg-surface shadow-card transition hover:border-primary/40 3xl:w-72">
          <Cover slug={i.primary_category} className="h-20" iconClass="size-14">
            <span className="absolute top-2 left-2 z-10 grid size-6 place-items-center rounded-md bg-black/45 text-xs font-bold text-white">{n + start}</span>
          </Cover>
          <div className="p-3">
            <Link to={`/article/${i.id}`} className="line-clamp-2 text-sm leading-snug font-semibold after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
              {i.title}
            </Link>
            <p className="mt-1.5 truncate text-xs text-muted-foreground">
              {source(i)} · {timeAgo(i.published_at)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}
