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
  ShieldCheck,
  Star,
  Sun,
  X,
} from 'lucide-react'
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router'

import { ListSkeleton } from '@/components/common'
import { categoryLook } from '@/lib/category'
import { Button } from '@/components/ui/button'
import { fieldClass } from '@/components/ui/input'
import { Tip } from '@/components/ui/tooltip'
import { useCategories } from '@/lib/format'
import { useTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

type NavItem = { to: string; label: string; icon: typeof Home; end?: boolean; short?: string }
const NAV_GROUPS: [string, NavItem[]][] = [
  [
    'Browse',
    [
      { to: '/', label: 'For You', icon: Home, end: true },
      { to: '/trending', label: 'Trending', icon: Flame },
      { to: '/relevant', label: 'Most relevant', icon: Star, short: 'Relevant' },
      { to: '/topics', label: 'Topics', icon: Grid2x2, end: true },
    ],
  ],
  ['Library', [{ to: '/bookmarks', label: 'Bookmarks', icon: Bookmark }]],
  [
    'Intelligence',
    [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/ask', label: 'Ask AI', icon: MessageCircleQuestion },
    ],
  ],
]
const NAV = NAV_GROUPS.flatMap(([, items]) => items)
const MOBILE_NAV = [NAV[0], NAV[1], NAV[3], NAV[4], NAV[6]]
const isAsk = (to: string) => to === '/ask'

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
    <form role="search" onSubmit={submit} className="relative w-full min-w-0 lg:max-w-2xl">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <label htmlFor="site-search" className="sr-only">
        Search NewsDC
      </label>
      <input
        id="site-search"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        maxLength={200}
        placeholder="Search news, research, companies…"
        className={cn(fieldClass, 'h-10 rounded-full bg-elevated/60 pr-9 pl-9 shadow-none hover:bg-surface focus-visible:bg-surface')}
      />
      <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded border bg-surface px-1.5 font-mono text-2xs text-muted-foreground md:block">
        /
      </kbd>
    </form>
  )
}

const navLink = ({ isActive }: { isActive: boolean }) =>
  cn(
    'relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-elevated hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none lg:py-1.5',
    isActive && 'bg-primary/12 font-medium text-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary',
  )

function GroupTitle({ children }: { children: string }) {
  return <h2 className="mb-1 px-3 text-2xs font-semibold tracking-wider text-muted-foreground uppercase">{children}</h2>
}

/** Full navigation: the desktop sidebar (≥ 1024 px) and the phone drawer. */
function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { topics } = useCategories()
  return (
    <nav aria-label="Main" className="flex min-h-full flex-col gap-5">
      {NAV_GROUPS.map(([group, items]) => (
        <div key={group}>
          <GroupTitle>{group}</GroupTitle>
          <ul className="space-y-0.5">
            {items.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={navLink} onClick={onNavigate}>
                  <Icon className={cn('size-4 shrink-0', isAsk(to) && 'text-ai')} aria-hidden />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {topics.length > 0 && (
        <div>
          <GroupTitle>Categories</GroupTitle>
          <ul className="space-y-0.5">
            {topics.map((t) => {
              const { Icon, style } = categoryLook(t.slug)
              return (
                <li key={t.slug}>
                  <NavLink to={`/topics/${t.slug}`} className={navLink} onClick={onNavigate} style={style}>
                    <Icon className="size-4 shrink-0 text-[oklch(0.62_0.15_var(--h))]" aria-hidden />
                    <span className="flex-1 truncate">{t.name}</span>
                    <span className="text-2xs text-muted-foreground tabular-nums">{t.item_count}</span>
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      <div className="mt-auto border-t pt-3">
        <NavLink to="/admin" className={navLink} onClick={onNavigate}>
          <ShieldCheck className="size-4 shrink-0" aria-hidden />
          Admin
        </NavLink>
      </div>
    </nav>
  )
}

/** Tablet (768–1023 px): an icon rail with hover labels. Categories live on the Topics page. */
function Rail() {
  return (
    <nav aria-label="Main" className="flex h-full flex-col items-center gap-1 py-3">
      {[...NAV, { to: '/admin', label: 'Admin', icon: ShieldCheck }].map(({ to, label, icon: Icon, end }, i) => (
        <Tip key={to} label={label} side="right">
          <NavLink
            to={to}
            end={end}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                'grid size-11 place-items-center rounded-xl text-foreground/75 transition-colors hover:bg-elevated hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                isActive && 'bg-primary/12 text-primary',
                i === NAV.length && 'mt-auto',
              )
            }
          >
            <Icon className={cn('size-5', isAsk(to) && 'text-ai')} aria-hidden />
          </NavLink>
        </Tip>
      ))}
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
    // `.shell` sets --sidebar-w per breakpoint (index.css); header and body share the same columns.
    <div className="shell min-h-dvh pb-[calc(4.25rem+env(safe-area-inset-bottom))] md:pb-0">
      <a href="#main" className="sr-only z-50 rounded bg-background p-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[var(--shell-max)] items-center gap-2 px-3 sm:px-4 md:grid md:grid-cols-[var(--sidebar-w)_minmax(0,1fr)_auto] md:gap-0 md:px-0">
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" onClick={() => drawer.current?.showModal()}>
            <Menu />
          </Button>
          <Link to="/" className="flex shrink-0 items-center gap-2.5 rounded-lg md:justify-center lg:justify-start lg:px-5">
            <span className="bg-brand grid size-9 place-items-center rounded-xl text-xs font-extrabold tracking-tight text-white shadow-card" aria-hidden>
              DC
            </span>
            <span className="hidden leading-tight lg:block">
              <span className="block text-base font-bold tracking-tight">NewsDC</span>
              <span className="block text-2xs font-medium text-muted-foreground">Data Center Intelligence</span>
            </span>
            <span className="sr-only lg:hidden">NewsDC home</span>
          </Link>
          <div className="flex min-w-0 flex-1 md:px-6 lg:px-8">
            <SearchBox key={urlQ} initial={urlQ} />
          </div>
          <div className="flex items-center gap-1 md:pr-4 lg:pr-6">
            <Button asChild variant="ai" size="sm" className="hidden sm:inline-flex">
              <Link to="/ask">
                <MessageCircleQuestion /> Ask AI
              </Link>
            </Button>
            <Tip label={`Theme: ${theme} (t)`} side="bottom">
              <Button variant="ghost" size="icon" onClick={() => setTheme(NEXT_THEME[theme])} aria-label={`Theme: ${theme}. Switch to ${NEXT_THEME[theme]}`}>
                <ThemeIcon />
              </Button>
            </Tip>
            <Tip label="Keyboard shortcuts (?)" side="bottom">
              <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={openHelp} aria-label="Keyboard shortcuts">
                <Keyboard />
              </Button>
            </Tip>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[var(--shell-max)] md:grid md:grid-cols-[var(--sidebar-w)_minmax(0,1fr)]">
        <aside className="sticky top-16 hidden h-[calc(100dvh-4rem)] border-r md:block lg:hidden">
          <Rail />
        </aside>
        <aside className="sticky top-16 hidden h-[calc(100dvh-4rem)] overflow-y-auto border-r px-3 py-5 lg:block">
          <Sidebar />
        </aside>
        <main id="main" tabIndex={-1} className="min-w-0 px-4 py-5 outline-none sm:px-6 lg:px-8 lg:py-6">
          <Suspense fallback={<ListSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden">
        <ul className="grid grid-cols-5">
          {MOBILE_NAV.map(({ to, label, short, icon: Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'group flex min-h-14 flex-col items-center justify-center gap-0.5 text-2xs focus-visible:outline-none',
                    isActive ? 'font-semibold text-primary' : 'text-muted-foreground',
                  )
                }
              >
                <span className="rounded-full px-4 py-1 group-focus-visible:ring-2 group-focus-visible:ring-ring group-aria-[current=page]:bg-primary/15">
                  <Icon className={cn('size-5', isAsk(to) && 'group-aria-[current=page]:text-ai')} aria-hidden />
                </span>
                {short ?? label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <dialog
        ref={drawer}
        aria-label="Menu"
        className="m-0 h-dvh max-h-none w-72 max-w-[85vw] overflow-y-auto border-r bg-surface px-3 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] text-foreground shadow-overlay"
        onClick={(e) => e.target === drawer.current && drawer.current.close()}
      >
        <div className="mb-4 flex items-center justify-between px-2">
          <span className="flex items-center gap-2 font-bold">
            <span className="bg-brand grid size-8 place-items-center rounded-lg text-xs font-extrabold text-white" aria-hidden>
              DC
            </span>
            NewsDC
          </span>
          <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => drawer.current?.close()}>
            <X />
          </Button>
        </div>
        <Sidebar onNavigate={() => drawer.current?.close()} />
      </dialog>
      <dialog
        ref={help}
        aria-labelledby="shortcuts-title"
        className="m-auto w-full max-w-md rounded-2xl border bg-surface p-5 text-foreground shadow-overlay"
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
                <kbd className="rounded border bg-elevated px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd className="text-muted-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      </dialog>
    </div>
  )
}
