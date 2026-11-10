import { Download } from 'lucide-react'

import { ItemCard } from '@/components/ItemCard'
import { CardGrid, EmptyState, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import type { ItemSummary } from '@/lib/api'
import { fmtDate, safeUrl, useTitle } from '@/lib/format'
import { useProfileState } from '@/lib/profile'

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

export default function BookmarksPage() {
  useTitle('Bookmarks')
  const { bookmarks } = useProfileState()
  return (
    <>
      <PageHeader title={`Bookmarks (${bookmarks.length})`}>
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
      <p className="-mt-2 mb-3 text-xs text-muted-foreground">Saved in this browser only.</p>
      {bookmarks.length === 0 ? (
        <EmptyState>No bookmarks yet. Press the bookmark icon (or b) on any article.</EmptyState>
      ) : (
        <CardGrid>
          {bookmarks.map((b) => (
            <ItemCard key={b.id} item={b} dismissible={false} />
          ))}
        </CardGrid>
      )}
    </>
  )
}
