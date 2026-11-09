import { Bookmark, BookmarkCheck, EyeOff, MessageSquare, Sparkles, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Quality, TypeBadge } from '@/components/common'
import type { ItemSummary } from '@/lib/api'
import { safeUrl, timeAgo, useCategories } from '@/lib/format'
import { profileStore, useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

type Props = {
  item: ItemSummary
  /** "Why am I seeing this?" (For You). */
  reason?: string
  /** Extra line under the title, e.g. a search snippet. */
  children?: ReactNode
  dismissible?: boolean
}

/** One feed row. `data-card` and the `data-*` actions are what the keyboard shortcuts drive. */
export function ItemCard({ item, reason, children, dismissible = true }: Props) {
  const { profile } = useProfileState()
  const { name } = useCategories()
  const read = profile.readIds.includes(item.id)
  const saved = profile.bookmarkIds.includes(item.id)
  const discussion = safeUrl(item.discussion_url)

  return (
    <article
      data-card
      data-original={safeUrl(item.url)}
      tabIndex={-1}
      aria-labelledby={`t-${item.id}`}
      className={cn(
        'group relative -mx-2 rounded-md px-2 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ring focus:bg-accent/60',
        read && 'opacity-60',
      )}
    >
      <div className="flex gap-2">
        <div className="min-w-0 flex-1">
          <h2 id={`t-${item.id}`} className="text-[15px] leading-snug font-medium">
            <Link data-open to={`/article/${item.id}`} className="hover:underline focus-visible:underline">
              {item.title}
            </Link>
            {read && <span className="sr-only"> (read)</span>}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="max-w-48 truncate">{item.publisher ?? item.source?.name}</span>
            <span aria-hidden>·</span>
            <time dateTime={item.published_at ?? undefined}>{timeAgo(item.published_at)}</time>
            {item.primary_category && (
              <Link
                to={`/topics/${item.primary_category}`}
                className="rounded-full border px-2 py-0.5 text-[11px] text-foreground hover:bg-accent"
              >
                {name(item.primary_category)}
              </Link>
            )}
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
              <a href={discussion} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 hover:underline">
                <MessageSquare className="size-3" aria-hidden />
                {item.comments_count}
                <span className="sr-only"> comments</span>
              </a>
            )}
          </div>
          {children ?? (item.summary && <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{item.summary}</p>)}
          {reason && (
            <p className="mt-1 inline-flex items-center gap-1 text-xs text-primary" title="Why am I seeing this?">
              <Sparkles className="size-3" aria-hidden />
              <span className="sr-only">Why you're seeing this: </span>
              {reason}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-center gap-1">
          <button
            data-bookmark
            type="button"
            onClick={() => profileStore.toggleBookmark(item)}
            aria-pressed={saved}
            aria-label={saved ? `Remove bookmark: ${item.title}` : `Bookmark: ${item.title}`}
            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {saved ? <BookmarkCheck className="size-4 text-primary" /> : <Bookmark className="size-4" />}
          </button>
          {dismissible && (
            <button
              data-dismiss
              type="button"
              onClick={() => profileStore.track('dismiss', item)}
              aria-label={`Not interested: ${item.title}`}
              title="Not interested"
              className="rounded p-1.5 text-muted-foreground opacity-100 hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 sm:focus-visible:opacity-100"
            >
              <EyeOff className="size-4" />
            </button>
          )}
        </div>
      </div>
    </article>
  )
}
