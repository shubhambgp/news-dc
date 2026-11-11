import { Bookmark, BookmarkCheck, EyeOff, MessageSquare, Sparkles, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Cover, Quality, TypeBadge } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Tip } from '@/components/ui/tooltip'
import type { ItemSummary } from '@/lib/api'
import { safeUrl, timeAgo, useCategories } from '@/lib/format'
import { profileStore, useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

export type CardLayout = 'card' | 'row'

type Props = {
  item: ItemSummary
  /** "Why am I seeing this?" (For You). */
  reason?: string
  /** Extra line under the title, e.g. a search snippet. */
  children?: ReactNode
  dismissible?: boolean
  /** A label on the artwork, e.g. "Discover". */
  kicker?: ReactNode
  /** `card`: artwork on top (grids). `row`: artwork on the left (compact list). */
  layout?: CardLayout
}

const iconBtn =
  'relative z-10 grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-elevated hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:size-8'

/** One feed item. The title link covers the whole card; the controls sit above it (`z-10`).
 * `data-card` and the `data-*` actions are what the keyboard shortcuts drive. */
export function ItemCard({ item, reason, children, dismissible = true, kicker, layout = 'card' }: Props) {
  const { profile } = useProfileState()
  const { name } = useCategories()
  const read = profile.readIds.includes(item.id)
  const saved = profile.bookmarkIds.includes(item.id)
  const discussion = safeUrl(item.discussion_url)
  const publisher = item.publisher ?? item.source?.name ?? ''
  const row = layout === 'row'

  const category = item.primary_category && (
    <Badge asChild variant="overlay" className="relative z-10 max-w-full truncate focus-visible:ring-white">
      <Link to={`/topics/${item.primary_category}`}>{name(item.primary_category)}</Link>
    </Badge>
  )
  const source = (
    <div className={cn('flex min-w-0 items-center gap-2 text-xs text-muted-foreground', row ? 'mt-2' : 'mt-auto pt-3')}>
      <span aria-hidden className="grid size-5 shrink-0 place-items-center rounded bg-elevated text-[10px] font-semibold text-foreground uppercase">
        {publisher.slice(0, 1)}
      </span>
      <span className="min-w-0 truncate font-medium text-foreground/80">{publisher}</span>
      <span aria-hidden>·</span>
      <time dateTime={item.published_at ?? undefined} className="shrink-0">
        {timeAgo(item.published_at)}
      </time>
    </div>
  )
  const meta = (
    <div className={cn('flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground', row ? 'mt-1.5' : 'mt-2')}>
      <TypeBadge type={item.content_type} />
      <Quality score={item.quality_score} />
      {item.points != null && item.points > 0 && (
        <span className="inline-flex items-center gap-0.5" title="Points">
          <TrendingUp className="size-3" aria-hidden />
          {item.points}
          <span className="sr-only"> points</span>
        </span>
      )}
      {item.comments_count != null && item.comments_count > 0 && discussion && (
        <a href={discussion} target="_blank" rel="noopener noreferrer" className="relative z-10 inline-flex min-h-6 min-w-6 items-center justify-center gap-0.5 hover:text-foreground hover:underline">
          <MessageSquare className="size-3" aria-hidden />
          {item.comments_count}
          <span className="sr-only"> comments</span>
        </a>
      )}
      <span className="ml-auto flex items-center">
        {dismissible && (
          <Tip label="Not interested">
            <button
              data-dismiss
              type="button"
              onClick={() => profileStore.track('dismiss', item)}
              aria-label={`Not interested: ${item.title}`}
              // Hidden until hover only where hover exists; touch screens always show it.
              className={cn(iconBtn, '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:group-focus-within:opacity-100 [@media(hover:hover)]:focus-visible:opacity-100')}
            >
              <EyeOff className="size-4" />
            </button>
          </Tip>
        )}
        <Tip label={saved ? 'Remove bookmark' : 'Bookmark'}>
          <button
            data-bookmark
            type="button"
            onClick={() => profileStore.toggleBookmark(item)}
            aria-pressed={saved}
            aria-label={saved ? `Remove bookmark: ${item.title}` : `Bookmark: ${item.title}`}
            className={iconBtn}
          >
            {saved ? <BookmarkCheck className="size-4 text-primary" /> : <Bookmark className="size-4" />}
          </button>
        </Tip>
      </span>
    </div>
  )
  const body = (
    <>
      <h2 id={`t-${item.id}`} className={cn('leading-snug font-semibold', row ? 'line-clamp-2 text-[15px]' : 'line-clamp-3 text-md')}>
        <Link data-open to={`/article/${item.id}`} className="after:absolute after:inset-0 focus-visible:underline focus-visible:outline-none">
          {item.title}
        </Link>
        {read && <span className="sr-only"> (read)</span>}
      </h2>
      {children ?? (item.summary && <p className={cn('mt-1.5 text-sm text-muted-foreground', row ? 'line-clamp-2 max-sm:hidden' : 'line-clamp-2')}>{item.summary}</p>)}
      {reason && (
        <p className="mt-2 inline-flex items-center gap-1 text-xs text-ai-ink">
          <Sparkles className="size-3 shrink-0" aria-hidden />
          <span className="sr-only">Why you're seeing this: </span>
          {reason}
        </p>
      )}
    </>
  )

  return (
    <article
      data-card
      data-original={safeUrl(item.url)}
      tabIndex={-1}
      aria-labelledby={`t-${item.id}`}
      className={cn(
        'group relative rounded-xl border bg-surface shadow-card outline-none transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring',
        'hover:border-primary/40 hover:shadow-raised focus-visible:ring-2 focus-visible:ring-ring focus:ring-2 focus:ring-ring',
        row ? 'flex gap-3 p-3 sm:gap-4' : 'flex h-full flex-col hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:hover:translate-y-0',
        read && 'opacity-60',
      )}
    >
      {row ? (
        <>
          <Cover slug={item.primary_category} className="w-24 shrink-0 self-stretch rounded-lg max-sm:min-h-20 sm:w-40" iconClass="size-12 -right-1 -bottom-2">
            {kicker && <div className="relative z-10 p-1.5">{kicker}</div>}
          </Cover>
          <div className="min-w-0 flex-1">
            {item.primary_category && <p className="mb-1 truncate text-2xs font-semibold tracking-wide text-primary-ink uppercase">{name(item.primary_category)}</p>}
            {body}
            {source}
            {meta}
          </div>
        </>
      ) : (
        <>
          <Cover slug={item.primary_category} className="aspect-[16/6] rounded-t-[calc(var(--radius-xl)-1px)]">
            <div className="relative z-10 flex items-start justify-between gap-2 p-3">
              {category || <span />}
              {kicker}
            </div>
          </Cover>
          <div className="flex flex-1 flex-col p-4">
            {body}
            {source}
            {meta}
          </div>
        </>
      )}
    </article>
  )
}
