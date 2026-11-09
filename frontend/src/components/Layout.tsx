import {
  Bookmark,
  Flame,
  Grid2x2,
  Home,
  Keyboard,
  LayoutDashboard,
  Menu,
  MessageCircleQuestion,
  Monitor,
  Moon,
  Search,
  Star,
  Sun,
  X,
} from 'lucide-react'
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router'

import { ListSkeleton } from '@/components/common'
import { Button } from '@/components/ui/button'
import { useCategories } from '@/lib/format'
import { useTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'For You', icon: Home, end: true },
  { to: '/trending', label: 'Trending', icon: Flame },
  { to: '/relevant', label: 'Most relevant', icon: Star },
  { to: '/topics', label: 'Topics', icon: Grid2x2, end: true },
  { to: '/bookmarks', label: 'Bookmarks', icon: Bookmark },
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/ask', label: 'Ask AI', icon: MessageCircleQuestion },
]
const MOBILE_NAV = [NAV[0], NAV[1], NAV[3], NAV[4], NAV[6]]

const SHORTCUTS: [string, string][] = [
  ['j / k', 'Next / previous item'],
  ['o or Enter', 'Open item'],
  ['Shift + O', 'Open original source'],
  ['b', 'Bookmark'],
  ['x', 'Not interested'],
  ['/', 'Focus search'],
  ['a', 'Ask AI'],
  ['t', 'Toggle theme'],
  ['g h', 'Go home'],
  ['g t', 'Go to Trending'],
  ['g p', 'Go to Topics'],
  ['g b', 'Go to Bookmarks'],
  ['g d', 'Go to Dashboard'],
  ['?', 'Show shortcuts'],
  ['Esc', 'Close / leave field'],
]
const GO: Record<string, string> = { h: '/', t: '/trending', p: '/topics', b: '/bookmarks', d: '/dashboard' }

const NEXT_THEME: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon }

const isTyping = (el: Element | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))

/** Global keyboard shortcuts. Item shortcuts act on the focused card (`[data-card]`, moved with
 * j/k) or, on an article page, on the article (`[data-card-page]`). */
function useShortcuts(openHelp: () => void) {
  const navigate = useNavigate()
  const { setTheme } = useTheme()
  const gAt = useRef(0)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === 'Escape') {
        if (isTyping(document.activeElement)) (document.activeElement as HTMLElement).blur()
        return
      }
      if (isTyping(document.activeElement) || document.querySelector('dialog[open]')) return

      const cards = [...document.querySelectorAll<HTMLElement>('[data-card]')]
      const current =
        (document.activeElement?.closest('[data-card]') as HTMLElement | null) ??
        document.querySelector<HTMLElement>('[data-card-page]')
      const act = (sel: string) => current?.querySelector<HTMLElement>(sel)
      const move = (d: number) => {
        if (!cards.length) return
        const i = current ? cards.indexOf(current) : -1
        const next = cards[Math.max(0, Math.min(cards.length - 1, i < 0 ? 0 : i + d))]
        next.focus({ preventScroll: true })
        next.scrollIntoView({ block: 'nearest' })
      }

      if (Date.now() - gAt.current < 1200 && GO[e.key]) {
        gAt.current = 0
        navigate(GO[e.key])
        e.preventDefault()
        return
      }
      const key = e.key
      const handlers: Record<string, () => void> = {
        j: () => move(1),
        k: () => move(-1),
        o: () => act('[data-open]')?.click(),
        Enter: () => {
          if (document.activeElement?.matches('[data-card]')) act('[data-open]')?.click()
        },
        O: () => {
          // A card carries the URL itself; the article page has a "Read original" link.
          const href = current?.dataset.original ?? act('[data-original]')?.getAttribute('href')
          if (href) window.open(href, '_blank', 'noopener,noreferrer')
        },
        b: () => act('[data-bookmark]')?.click(),
        x: () => {
          const i = current ? cards.indexOf(current) : -1
          act('[data-dismiss]')?.click()
          // Keep the keyboard position: focus what is now at the same index.
          requestAnimationFrame(() => document.querySelectorAll<HTMLElement>('[data-card]')[i]?.focus())
        },
        '/': () => document.getElementById('site-search')?.focus(),
        a: () => navigate('/ask'),
        t: () => setTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark'),
        g: () => {
          gAt.current = Date.now()
        },
        '?': openHelp,
      }
      const h = handlers[key]
      if (!h) return
      // Enter on a focused link or button keeps its default behaviour.
      if (key === 'Enter' && !document.activeElement?.matches('[data-card]')) return
      e.preventDefault()
      h()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [navigate, setTheme, openHelp])
}

/** Remounted (via `key`) when the URL's query changes, so the box shows the current search. */
function SearchBox({ initial }: { initial: string }) {
  const navigate = useNavigate()
  const [q, setQ] = useState(initial)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`)
  }
  return (
    <form role="search" onSubmit={submit} className="relative min-w-0 flex-1 sm:max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <label htmlFor="site-search" className="sr-only">
        Search NewsDC
      </label>
      <input
        id="site-search"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        maxLength={200}
        placeholder="Search data center news…"
        className="h-9 w-full rounded-md border bg-background pr-8 pl-8 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 rounded border px-1 text-[10px] text-muted-foreground sm:block">
        /
      </kbd>
    </form>
  )
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { topics } = useCategories()
  const link = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
      isActive && 'bg-accent font-medium',
    )
  return (
    <nav aria-label="Main" className="space-y-6">
      <ul className="space-y-0.5">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink to={to} end={end} className={link} onClick={onNavigate}>
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      {topics.length > 0 && (
        <div>
          <h2 className="mb-1 px-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Categories</h2>
          <ul className="space-y-0.5">
            {topics.map((t) => (
              <li key={t.slug}>
                <NavLink to={`/topics/${t.slug}`} className={link} onClick={onNavigate}>
                  <span className="flex-1 truncate">{t.name}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{t.item_count}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="px-2 text-xs text-muted-foreground">
        <Link to="/admin" className="hover:underline" onClick={onNavigate}>
          Admin
        </Link>
      </p>
    </nav>
  )
}

export function Layout() {
  const { theme, setTheme } = useTheme()
  const ThemeIcon = THEME_ICON[theme]
  const help = useRef<HTMLDialogElement>(null)
  const drawer = useRef<HTMLDialogElement>(null)
  const { pathname } = useLocation()
  const [sp] = useSearchParams()
  const urlQ = pathname === '/search' ? (sp.get('q') ?? '') : ''
  const openHelp = useCallback(() => help.current?.showModal(), [])
  useShortcuts(openHelp)

  // New page: back to the top (the browser restores position on back/forward via history).
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="min-h-screen pb-16 lg:pb-0">
      <a href="#main" className="sr-only z-50 rounded bg-background p-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-3 sm:gap-3 sm:px-4">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => drawer.current?.showModal()}>
            <Menu />
          </Button>
          <Link to="/" className="flex shrink-0 items-center gap-1.5 text-lg font-bold tracking-tight">
            <span className="grid size-6 place-items-center rounded bg-primary text-xs text-primary-foreground" aria-hidden>
              DC
            </span>
            <span className="hidden sm:inline">NewsDC</span>
            <span className="sr-only sm:hidden">NewsDC home</span>
          </Link>
          <SearchBox key={urlQ} initial={urlQ} />
          <Button asChild size="sm" className="hidden sm:inline-flex">
            <Link to="/ask">
              <MessageCircleQuestion /> Ask AI
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(NEXT_THEME[theme])}
            aria-label={`Theme: ${theme}. Switch to ${NEXT_THEME[theme]}`}
            title={`Theme: ${theme}`}
          >
            <ThemeIcon />
          </Button>
          <Button variant="ghost" size="icon" className="hidden sm:inline-flex" onClick={openHelp} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
            <Keyboard />
          </Button>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-3 sm:px-4">
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 overflow-y-auto py-4 lg:block">
          <Sidebar />
        </aside>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 py-4 outline-none">
          <Suspense fallback={<ListSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-30 border-t bg-background lg:hidden">
        <ul className="grid grid-cols-5">
          {MOBILE_NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn('flex flex-col items-center gap-0.5 py-2 text-[11px]', isActive ? 'font-medium text-foreground' : 'text-muted-foreground')
                }
              >
                <Icon className="size-5" aria-hidden />
                {label === 'Most relevant' ? 'Relevant' : label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <dialog
        ref={drawer}
        aria-label="Menu"
        className="m-0 h-full max-h-none w-72 max-w-[85vw] bg-background p-4 text-foreground backdrop:bg-black/40"
        onClick={(e) => e.target === drawer.current && drawer.current.close()}
      >
        <div className="mb-4 flex items-center justify-between">
          <span className="font-bold">NewsDC</span>
          <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => drawer.current?.close()}>
            <X />
          </Button>
        </div>
        <Sidebar onNavigate={() => drawer.current?.close()} />
      </dialog>

      <dialog
        ref={help}
        aria-labelledby="shortcuts-title"
        className="m-auto w-full max-w-md rounded-lg border bg-background p-5 text-foreground backdrop:bg-black/40"
        onClick={(e) => e.target === help.current && help.current.close()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id="shortcuts-title" className="font-semibold">
            Keyboard shortcuts
          </h2>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={() => help.current?.close()}>
            <X />
          </Button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd className="text-muted-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      </dialog>
    </div>
  )
}
