// The anonymous reading profile kept in localStorage (Phase 5 contract, docs/ARCHITECTURE.md).
// Pure functions first (unit tested in profile.test.ts), then a tiny reactive store around them.
import { useSyncExternalStore } from 'react'

import type { ItemSummary } from './api'

export type Profile = {
  categoryWeights: Record<string, number>
  tagWeights: Record<string, number>
  readIds: number[] // oldest first
  bookmarkIds: number[]
  dismissedIds: number[]
  explicitTopics: string[]
  onboarded: boolean
  decayedAt: number // ms epoch of the last daily decay
}

// Server limits (docs/API.md "For You").
export const LIMITS = { categories: 64, tags: 100, read: 200, bookmarks: 500, dismissed: 500, topics: 64 }
export const EVENT_WEIGHT = { open: 1, read: 2, bookmark: 3, dismiss: -3 } as const
export type ProfileEvent = keyof typeof EVENT_WEIGHT
const DAY = 86_400_000
const DECAY = 0.95
const MAX_WEIGHT = 1000
const MIN_WEIGHT = 0.01 // smaller weights are dropped after decay

export const emptyProfile = (now = Date.now()): Profile => ({
  categoryWeights: {},
  tagWeights: {},
  readIds: [],
  bookmarkIds: [],
  dismissedIds: [],
  explicitTopics: [],
  onboarded: false,
  decayedAt: now,
})

/** Keep the `limit` entries with the largest |weight|, rounded and clamped to ±1000. */
function trimWeights(w: Record<string, number>, limit: number): Record<string, number> {
  return Object.fromEntries(
    Object.entries(w)
      .map(([k, v]) => [k, Math.max(-MAX_WEIGHT, Math.min(MAX_WEIGHT, Math.round(v * 1000) / 1000))] as const)
      .filter(([, v]) => Number.isFinite(v) && Math.abs(v) >= MIN_WEIGHT)
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
      .slice(0, limit),
  )
}

/** Append `id`, moving it to the end if present; keep the newest `limit`. */
function pushId(ids: number[], id: number, limit: number): number[] {
  return [...ids.filter((x) => x !== id), id].slice(-limit)
}

/** Weights decay ×0.95 per whole day elapsed since the last decay. */
export function decay(p: Profile, now = Date.now()): Profile {
  const days = Math.floor((now - p.decayedAt) / DAY)
  if (days < 1) return p
  const f = DECAY ** days
  const scale = (w: Record<string, number>) => Object.fromEntries(Object.entries(w).map(([k, v]) => [k, v * f]))
  return {
    ...p,
    categoryWeights: trimWeights(scale(p.categoryWeights), LIMITS.categories),
    tagWeights: trimWeights(scale(p.tagWeights), LIMITS.tags),
    decayedAt: p.decayedAt + days * DAY,
  }
}

/** Apply one reading event to the item's categories and tags (open +1, read >30 s +2, bookmark +3,
 * not interested −3) and to the matching ID list. */
export function applyEvent(p: Profile, event: ProfileEvent, item: Pick<ItemSummary, 'id' | 'categories' | 'tags'>): Profile {
  const delta = EVENT_WEIGHT[event]
  const cw = { ...p.categoryWeights }
  const tw = { ...p.tagWeights }
  for (const c of item.categories) cw[c] = (cw[c] ?? 0) + delta
  for (const t of item.tags) if (t.length >= 1 && t.length <= 64) tw[t] = (tw[t] ?? 0) + delta
  const next: Profile = {
    ...p,
    categoryWeights: trimWeights(cw, LIMITS.categories),
    tagWeights: trimWeights(tw, LIMITS.tags),
  }
  if (event === 'open' || event === 'read') next.readIds = pushId(p.readIds, item.id, LIMITS.read)
  if (event === 'bookmark') next.bookmarkIds = pushId(p.bookmarkIds, item.id, LIMITS.bookmarks)
  if (event === 'dismiss') next.dismissedIds = pushId(p.dismissedIds, item.id, LIMITS.dismissed)
  return next
}

export function removeBookmark(p: Profile, id: number): Profile {
  return { ...p, bookmarkIds: p.bookmarkIds.filter((x) => x !== id) }
}

export function setTopics(p: Profile, topics: string[]): Profile {
  return { ...p, explicitTopics: [...new Set(topics)].slice(0, LIMITS.topics), onboarded: true }
}

/** The body for POST /feeds/foryou: only the fields the server accepts. Unknown category slugs
 * (e.g. a category deleted since) are dropped so the server doesn't answer 422. */
export function toRequest(p: Profile, knownCategories?: Set<string>) {
  const known = (s: string) => !knownCategories || knownCategories.has(s)
  return {
    categoryWeights: Object.fromEntries(Object.entries(p.categoryWeights).filter(([k]) => known(k))),
    tagWeights: p.tagWeights,
    readIds: p.readIds,
    bookmarkIds: p.bookmarkIds,
    dismissedIds: p.dismissedIds,
    explicitTopics: p.explicitTopics.filter(known),
  }
}

/** Parse whatever is stored; anything malformed falls back to an empty profile field by field. */
export function parseProfile(raw: string | null, now = Date.now()): Profile {
  const base = emptyProfile(now)
  if (!raw) return base
  try {
    const v = JSON.parse(raw)
    const ids = (x: unknown, limit: number) =>
      Array.isArray(x) ? x.filter((n) => Number.isSafeInteger(n) && n > 0).slice(-limit) : []
    const weights = (x: unknown, limit: number) =>
      x && typeof x === 'object' && !Array.isArray(x)
        ? trimWeights(Object.fromEntries(Object.entries(x).filter(([, n]) => typeof n === 'number')), limit)
        : {}
    return decay(
      {
        categoryWeights: weights(v.categoryWeights, LIMITS.categories),
        tagWeights: weights(v.tagWeights, LIMITS.tags),
        readIds: ids(v.readIds, LIMITS.read),
        bookmarkIds: ids(v.bookmarkIds, LIMITS.bookmarks),
        dismissedIds: ids(v.dismissedIds, LIMITS.dismissed),
        explicitTopics: Array.isArray(v.explicitTopics)
          ? v.explicitTopics.filter((s: unknown) => typeof s === 'string').slice(0, LIMITS.topics)
          : [],
        onboarded: v.onboarded === true,
        decayedAt: Number.isFinite(v.decayedAt) && v.decayedAt <= now ? v.decayedAt : now,
      },
      now,
    )
  } catch {
    return base
  }
}

// --- Store ----------------------------------------------------------------------------------

const PROFILE_KEY = 'newsdc-profile'
const BOOKMARKS_KEY = 'newsdc-bookmarks' // the bookmarked items themselves, newest first

function load<T>(key: string, parse: (raw: string | null) => T): T {
  try {
    return parse(localStorage.getItem(key))
  } catch {
    return parse(null) // storage blocked (private mode): the app still works, nothing persists
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // quota or blocked storage: non-fatal
  }
}

function parseBookmarks(raw: string | null): ItemSummary[] {
  try {
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v.filter((x) => x && Number.isSafeInteger(x.id) && typeof x.title === 'string') : []
  } catch {
    return []
  }
}

type State = { profile: Profile; bookmarks: ItemSummary[] }
let state: State = {
  profile: load(PROFILE_KEY, (r) => parseProfile(r)),
  bookmarks: load(BOOKMARKS_KEY, parseBookmarks),
}
const listeners = new Set<() => void>()

function set(next: Partial<State>) {
  state = { ...state, ...next }
  if (next.profile) save(PROFILE_KEY, state.profile)
  if (next.bookmarks) save(BOOKMARKS_KEY, state.bookmarks)
  listeners.forEach((l) => l())
}

// Other tabs: pick up their changes.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === PROFILE_KEY) set({ profile: parseProfile(e.newValue) })
    if (e.key === BOOKMARKS_KEY) set({ bookmarks: parseBookmarks(e.newValue) })
  })
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useProfileState(): State {
  return useSyncExternalStore(subscribe, () => state)
}

export const profileStore = {
  get: () => state,
  track(event: ProfileEvent, item: ItemSummary) {
    set({ profile: applyEvent(state.profile, event, item) })
  },
  toggleBookmark(item: ItemSummary) {
    if (state.profile.bookmarkIds.includes(item.id)) {
      set({ profile: removeBookmark(state.profile, item.id), bookmarks: state.bookmarks.filter((b) => b.id !== item.id) })
    } else {
      // Keep the card fields only (ItemDetail has more), newest first.
      const card: ItemSummary = {
        id: item.id,
        title: item.title,
        url: item.url,
        publisher: item.publisher,
        author: item.author,
        published_at: item.published_at,
        source: item.source,
        primary_category: item.primary_category,
        categories: item.categories,
        content_type: item.content_type,
        summary: item.summary,
        tags: item.tags,
        relevance_score: item.relevance_score,
        quality_score: item.quality_score,
        points: item.points,
        comments_count: item.comments_count,
        discussion_url: item.discussion_url,
      }
      set({
        profile: applyEvent(state.profile, 'bookmark', item),
        bookmarks: [card, ...state.bookmarks.filter((b) => b.id !== item.id)].slice(0, LIMITS.bookmarks),
      })
    }
  },
  setTopics(topics: string[]) {
    set({ profile: setTopics(state.profile, topics) })
  },
  /** "Reset my preferences": weights, history and topics. Bookmarks stay. */
  reset() {
    set({ profile: { ...emptyProfile(), bookmarkIds: state.profile.bookmarkIds } })
  },
}
