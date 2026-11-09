import { useSearchParams } from 'react-router'

import { Feed, Filters } from '@/components/Feed'
import { useFilterParams } from '@/lib/filters'
import { ItemCard } from '@/components/ItemCard'
import { EmptyState, PageHeader } from '@/components/common'
import { api, type SearchHit } from '@/lib/api'
import { useTitle } from '@/lib/format'

/** The API's snippet is HTML-escaped with only <mark>…</mark> added (docs/API.md); render it
 * without innerHTML anyway by splitting on the marks. */
function Snippet({ html }: { html: string }) {
  const decode = (s: string) => new DOMParser().parseFromString(s, 'text/html').documentElement.textContent ?? ''
  const parts = html.split(/<mark>|<\/mark>/)
  return (
    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
      {parts.map((p, i) =>
        i % 2 ? (
          <mark key={i} className="rounded-sm bg-yellow-200 px-0.5 text-foreground dark:bg-yellow-700/60">
            {decode(p)}
          </mark>
        ) : (
          decode(p)
        ),
      )}
    </p>
  )
}

export default function SearchPage() {
  const [sp, setSp] = useSearchParams()
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

  return (
    <>
      <PageHeader title={q ? `Results for “${q}”` : 'Search'} />
      <Filters>
        <select aria-label="Sort" className="h-8 rounded-md border bg-background px-2 text-sm" value={sort} onChange={(e) => set('sort', e.target.value === 'latest' ? 'latest' : '')}>
          <option value="relevance">Best match</option>
          <option value="latest">Newest</option>
        </select>
        <label className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
          From
          <input type="date" value={from} max={to || undefined} onChange={(e) => set('from', e.target.value)} className="h-8 min-w-0 flex-1 rounded-md border bg-background px-1 text-sm text-foreground" />
        </label>
        <label className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
          To
          <input type="date" value={to} min={from || undefined} onChange={(e) => set('to', e.target.value)} className="h-8 min-w-0 flex-1 rounded-md border bg-background px-1 text-sm text-foreground" />
        </label>
      </Filters>
      {!q ? (
        <EmptyState>Type a search above. Use "quotes" for a phrase and -word to exclude a word.</EmptyState>
      ) : badRange ? (
        <EmptyState>The end date is before the start date.</EmptyState>
      ) : (
        <Feed<SearchHit>
          queryKey={['search', q, filters, sort, range]}
          fetchPage={(page) => api.search({ q, ...filters, ...range, sort, page })}
          empty={`No results for “${q}”. Try fewer words or remove a filter.`}
          render={(h) => (
            <ItemCard item={h}>
              <Snippet html={h.snippet} />
            </ItemCard>
          )}
        />
      )}
    </>
  )
}
