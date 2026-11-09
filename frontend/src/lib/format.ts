import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api } from './api'

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31_536_000],
  ['month', 2_592_000],
  ['week', 604_800],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' })

export function timeAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const s = (new Date(iso).getTime() - now) / 1000
  for (const [unit, secs] of UNITS) if (Math.abs(s) >= secs) return rtf.format(Math.round(s / secs), unit)
  return 'just now'
}

export const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en', { year: 'numeric', month: 'short', day: 'numeric' }) : ''

export const fmtUsd = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`

/** Only http(s) links are rendered as links (sources and model output are untrusted). */
export const safeUrl = (u: string | null | undefined) => (u && /^https?:\/\//i.test(u) ? u : undefined)

/** Category slugs → names, from /topics (cached for the session). */
export function useCategories() {
  const q = useQuery({ queryKey: ['topics'], queryFn: api.topics, staleTime: 10 * 60_000 })
  const names = new Map((q.data ?? []).map((t) => [t.slug, t.name]))
  return { topics: q.data ?? [], name: (slug: string | null) => (slug ? (names.get(slug) ?? slug) : ''), query: q }
}

/** Sources for the filter dropdown, from /stats (cached). */
export function useSources() {
  const q = useQuery({ queryKey: ['stats'], queryFn: api.stats, staleTime: 5 * 60_000 })
  return (q.data?.by_source ?? []).filter((s) => s.processed > 0)
}

export function useTitle(title: string, description?: string) {
  useEffect(() => {
    document.title = title ? `${title} · NewsDC` : 'NewsDC: Data Center news, filtered by AI'
    if (description) document.querySelector('meta[name="description"]')?.setAttribute('content', description)
  }, [title, description])
}
