import { Search as SearchIcon } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { Feed, Filters, ViewToggle } from '@/components/Feed'
import { ItemCard } from '@/components/ItemCard'
import { PageHeader } from '@/components/common'
import { fieldClass } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { api, type SearchHit } from '@/lib/api'
import { useFilterParams, useView } from '@/lib/filters'
import { useTitle } from '@/lib/format'
import { cn } from '@/lib/utils'

/** The API's snippet is HTML-escaped with only <mark>…</mark> added (docs/API.md); render it
 * without innerHTML anyway by splitting on the marks. */
function Snippet({ html }: { html: string }) {
  const decode = (s: string) => new DOMParser().parseFromString(s, 'text/html').documentElement.textContent ?? ''
  const parts = html.split(/<mark>|<\/mark>/)
  return (
    <p className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">
      {parts.map((p, i) =>
        i % 2 ? (
          <mark key={i} className="rounded-sm bg-warning/25 px-0.5 font-medium text-foreground">
            {decode(p)}
          </mark>
        ) : (
          decode(p)
        ),
      )}
    </p>
  )
}

// Starting points for an empty search box (UI hints, not data).
const EXAMPLES = ['liquid cooling', 'small modular reactor', 'GPU cluster', 'PUE', '"power purchase agreement"', 'interconnection queue']

export default function SearchPage() {
  const [sp, setSp] = useSearchParams()
  const [view] = useView()
  const q = (sp.get('q') ?? '').trim()
  const sort = sp.get('sort') === 'latest' ? 'latest' : 'relevance'
  const from = sp.get('from') ?? ''
  const to = sp.get('to') ?? ''
  const filters = useFilterParams()
  useTitle(q ? `Search: ${q}` : 'Search')

  const set = (k: string, v: string) =>
    setSp(
      (p) => {
        const n = new URLSearchParams(p)
        if (v) n.set(k, v)
        else n.delete(k)
        return n
      },
      { replace: true },
    )
  // Dates are picked as local days; the API wants UTC timestamps (`to` is exclusive).
  const dayStart = (d: string) => (d ? new Date(`${d}T00:00:00`).toISOString() : undefined)
  const dayEnd = (d: string) => (d ? new Date(new Date(`${d}T00:00:00`).getTime() + 86_400_000).toISOString() : undefined)
  const range = { from: dayStart(from), to: dayEnd(to) }
  const badRange = !!(from && to && to < from)
  const dateCls = cn(fieldClass, 'h-10 min-w-0 flex-1 px-2 md:h-9 md:w-40 md:flex-none')

  return (
    <>
      <PageHeader
        title={q ? `Results for “${q}”` : 'Search'}
        icon={SearchIcon}
        description="Hybrid search: keywords in titles, text and AI summaries, combined with semantic similarity. Use “quotes” for a phrase and -word to exclude a word."
      />
      <Filters
        toolbar={
          <>
            <Segmented
              label="Sort"
              value={sort}
              onChange={(v) => set('sort', v === 'latest' ? 'latest' : '')}
              options={[
                ['relevance', 'Best match'],
                ['latest', 'Newest'],
              ]}
            />
            <ViewToggle />
          </>
        }
      >
        <label className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
          From
          <input type="date" value={from} max={to || undefined} onChange={(e) => set('from', e.target.value)} className={dateCls} />
        </label>
        <label className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
          To
          <input type="date" value={to} min={from || undefined} onChange={(e) => set('to', e.target.value)} className={dateCls} />
        </label>
      </Filters>
      {!q ? (
        <div className="rounded-2xl border border-dashed bg-surface/60 p-8 text-center">
          <p className="text-sm text-muted-foreground">Type a search in the box at the top, or start with one of these:</p>
          <ul className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((e) => (
              <li key={e}>
                <Link
                  to={`/search?q=${encodeURIComponent(e)}`}
                  className="inline-flex h-9 items-center rounded-full border bg-surface px-3 text-sm hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {e}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : badRange ? (
        <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive-ink">
          The end date is before the start date.
        </p>
      ) : (
        <Feed<SearchHit>
          queryKey={['search', q, filters, sort, range]}
          fetchPage={(page) => api.search({ q, ...filters, ...range, sort, page })}
          empty={`No results for “${q}”. Try fewer words or remove a filter.`}
          layout={view}
          countNoun="results"
          render={(h, layout) => (
            <ItemCard item={h} layout={layout}>
              <Snippet html={h.snippet} />
            </ItemCard>
          )}
        />
      )}
    </>
  )
}
