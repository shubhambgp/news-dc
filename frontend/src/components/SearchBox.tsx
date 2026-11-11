import { Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { fieldClass } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** Site search. Remounted (via `key`) when the URL's query changes, so the box shows the current
 * search. The header instance has id `site-search`, which the `/` shortcut focuses. */
export function SearchBox({ id, initial = '', className, large }: { id: string; initial?: string; className?: string; large?: boolean }) {
  const navigate = useNavigate()
  const [q, setQ] = useState(initial)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`)
  }
  return (
    <form role="search" onSubmit={submit} className={cn('relative w-full min-w-0 lg:max-w-2xl', className)}>
      <Search className={cn('pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground', large ? 'left-4 size-5' : 'size-4')} aria-hidden />
      <label htmlFor={id} className="sr-only">
        Search NewsDC
      </label>
      <input
        id={id}
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        maxLength={200}
        placeholder="Search news, research, companies…"
        className={cn(
          fieldClass,
          'rounded-full pr-9',
          large ? 'h-12 pl-12 text-base' : 'h-10 bg-elevated/60 pl-9 shadow-none hover:bg-surface focus-visible:bg-surface',
        )}
      />
      {!large && (
        <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded border bg-surface px-1.5 font-mono text-2xs text-muted-foreground md:block">
          /
        </kbd>
      )}
    </form>
  )
}
