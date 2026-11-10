import { Bookmark, Download, Flame, Home, Search, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { ViewToggle } from '@/components/Feed'
import { ItemCard } from '@/components/ItemCard'
import { CardGrid, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { fieldClass, Select } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { CONTENT_TYPES, type ItemSummary } from '@/lib/api'
import { useSetParam, useView } from '@/lib/filters'
import { fmtDate, safeUrl, useCategories, useTitle } from '@/lib/format'
import { useProfileState } from '@/lib/profile'
import { cn } from '@/lib/utils'

/** Escape Markdown markup in untrusted text (titles and summaries come from sources and the model). */
const esc = (s: string) => s.replace(/[\\`*_{}[\]()#+\-.!|<>~]/g, '\\$&').replace(/\s+/g, ' ')

function bookmarksToMarkdown(items: ItemSummary[]): string {
  const lines = ['# NewsDC bookmarks', '', `Exported ${new Date().toISOString().slice(0, 10)}, ${items.length} items.`, '']
  for (const i of items) {
    const url = safeUrl(i.url)
    lines.push(url ? `## [${esc(i.title)}](<${url.replace(/>/g, '%3E')}>)` : `## ${esc(i.title)}`)
    lines.push('', `${esc(i.publisher ?? '')} · ${fmtDate(i.published_at)} · ${i.content_type ?? ''}`, '')
    if (i.summary) lines.push(esc(i.summary), '')
  }
  return lines.join('\n')
}

function download(name: string, type: string, text: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

const SORTS = [
  ['saved', 'Recently saved'],
  ['published', 'Newest'],
] as const

function Empty() {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed bg-surface/60 px-6 py-14 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-primary/12 text-primary" aria-hidden>
        <Bookmark className="size-6" />
      </span>
      <h2 className="mt-4 text-lg font-semibold">Nothing saved yet</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        Press the bookmark icon on any article, or <kbd className="rounded border bg-elevated px-1 font-mono text-xs">b</kbd> on a focused card. Bookmarks stay in this browser.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Button asChild variant="outline" size="sm">
          <Link to="/">
            <Home /> For You
          </Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link to="/trending">
            <Flame /> Trending
          </Link>
        </Button>
      </div>
    </div>
  )
}

export default function BookmarksPage() {
  useTitle('Bookmarks')
  const { bookmarks } = useProfileState()
  const { name } = useCategories()
  const [view] = useView()
  const [sp, set] = useSetParam()
  const [, setSp] = useSearchParams()
  // Filters run in the browser over the saved items (stored newest first); nothing is sent anywhere.
  const find = (sp.get('find') ?? '').trim().toLowerCase()
  const type = sp.get('content_type') ?? ''
  const cat = sp.get('category') ?? ''
  const sort = sp.get('sort') === 'published' ? 'published' : 'saved'
  const cats = [...new Set(bookmarks.map((b) => b.primary_category).filter((c): c is string => !!c))]
  const shown = bookmarks
    .filter((b) => (!type || b.content_type === type) && (!cat || b.primary_category === cat))
    .filter((b) => !find || `${b.title} ${b.summary ?? ''} ${b.publisher ?? ''}`.toLowerCase().includes(find))
  if (sort === 'published') shown.sort((a, b) => (b.published_at ?? '').localeCompare(a.published_at ?? ''))
  const filtered = !!(find || type || cat)

  return (
    <>
      <PageHeader title="Bookmarks" icon={Bookmark} description={`${bookmarks.length} saved in this browser only. Export them before clearing site data.`}>
        {bookmarks.length > 0 && (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => download('newsdc_bookmarks.json', 'application/json', JSON.stringify(bookmarks, null, 2))}>
              <Download /> JSON
            </Button>
            <Button variant="outline" size="sm" onClick={() => download('newsdc_bookmarks.md', 'text/markdown', bookmarksToMarkdown(bookmarks))}>
              <Download /> Markdown
            </Button>
          </div>
        )}
      </PageHeader>
      {bookmarks.length === 0 ? (
        <Empty />
      ) : (
        <>
          <form role="search" aria-label="Filter bookmarks" onSubmit={(e) => e.preventDefault()} className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border bg-surface p-2.5 shadow-card">
            <label className="relative min-w-0 flex-1 basis-56">
              <span className="sr-only">Find in bookmarks</span>
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input type="search" value={sp.get('find') ?? ''} onChange={(e) => set('find', e.target.value)} placeholder="Find in bookmarks…" className={cn(fieldClass, 'h-10 pl-9 md:h-9')} />
            </label>
            <Select aria-label="Content type" className="min-w-0 flex-1 basis-32 md:w-auto md:flex-none" value={type} onChange={(e) => set('content_type', e.target.value)}>
              <option value="">All types</option>
              {CONTENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </Select>
            {cats.length > 1 && (
              <Select aria-label="Category" className="min-w-0 flex-1 basis-32 md:w-auto md:max-w-56 md:flex-none" value={cat} onChange={(e) => set('category', e.target.value)}>
                <option value="">All categories</option>
                {cats.map((c) => (
                  <option key={c} value={c}>
                    {name(c)}
                  </option>
                ))}
              </Select>
            )}
            <Segmented label="Sort" value={sort} onChange={(v) => set('sort', v === 'published' ? 'published' : '')} options={SORTS} />
            <ViewToggle />
          </form>
          <p className="mb-3 text-xs text-muted-foreground" aria-live="polite">
            {filtered ? `${shown.length} of ${bookmarks.length} bookmarks` : `${bookmarks.length} bookmarks`}
          </p>
          {shown.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              No bookmarks match these filters.
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setSp(
                    (p) => {
                      const n = new URLSearchParams(p)
                      for (const k of ['find', 'content_type', 'category']) n.delete(k)
                      return n
                    },
                    { replace: true },
                  )
                }
              >
                <X /> Clear filters
              </Button>
            </div>
          ) : view === 'row' ? (
            <ul className="space-y-3">
              {shown.map((b) => (
                <li key={b.id}>
                  <ItemCard item={b} dismissible={false} layout="row" />
                </li>
              ))}
            </ul>
          ) : (
            <CardGrid>
              {shown.map((b) => (
                <ItemCard key={b.id} item={b} dismissible={false} />
              ))}
            </CardGrid>
          )}
        </>
      )}
    </>
  )
}
