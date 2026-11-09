// Typed client for the NewsDC API (docs/API.md). The frontend talks to the backend only over HTTP.
// Empty base = same origin (production behind Caddy). Dev sets http://localhost:8000.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const V1 = `${API_BASE}/api/v1`

export type ContentType = 'news' | 'research' | 'investment' | 'engineering'
export const CONTENT_TYPES: ContentType[] = ['news', 'research', 'investment', 'engineering']

export type SourceRef = { key: string; name: string }

export type ItemSummary = {
  id: number
  title: string
  url: string
  publisher: string | null
  author: string | null
  published_at: string | null
  source: SourceRef | null
  primary_category: string | null
  categories: string[]
  content_type: ContentType | null
  summary: string | null
  tags: string[]
  relevance_score: number | null
  quality_score: number | null
  points: number | null
  comments_count: number | null
  discussion_url: string | null
}

export type Page<T> = { items: T[]; page: number; page_size: number; total: number; has_more: boolean }

export type KeyInsight = { type: 'technical' | 'business'; text: string }
export type Coverage = {
  source: SourceRef
  url: string
  title: string | null
  published_at: string | null
  first_seen_at: string
  engagement: Record<string, unknown>
  is_primary: boolean
}
export type DuplicateRef = {
  id: number
  title: string
  url: string
  publisher: string | null
  published_at: string | null
  similarity: number | null
}
export type ItemDetail = ItemSummary & {
  description: string | null
  key_insights: KeyInsight[]
  entities: { companies: string[]; technologies: string[]; locations: string[] }
  related_links: unknown[]
  coverage: Coverage[]
  also_covered_by: DuplicateRef[]
}
export type RelatedItem = ItemSummary & { similarity: number; score: number }
export type SearchHit = ItemSummary & { snippet: string; score: number }
export type SearchPage = Page<SearchHit> & { mode: 'hybrid' | 'keyword' }
export type ForYouItem = ItemSummary & {
  kind: 'personal' | 'discover' | 'trending' | 'relevant'
  reason: string
  score: number
}
export type ForYouPage = Page<ForYouItem> & { cold_start: boolean }

export type TopicSummary = {
  slug: string
  name: string
  description: string
  item_count: number
  latest: ItemSummary[]
}
export type TopicPage = { slug: string; name: string; description: string; items: Page<ItemSummary> }

export type Citation = {
  n: number
  id: number
  title: string
  url: string
  publisher: string | null
  published_at: string | null
}
export type AskSource = Citation & {
  source: SourceRef | null
  primary_category: string | null
  content_type: ContentType | null
}

export type RisingTerm = { term: string; recent: number; baseline: number; change_pct: number; new: boolean }
export type TrendBrief = {
  id: number
  period_start: string
  period_end: string
  content_md: string
  sources: Citation[]
  model: string | null
  created_at: string
}
export type Trends = {
  recent_start: string
  baseline_start: string
  now: string
  tags: RisingTerm[]
  companies: RisingTerm[]
  technologies: RisingTerm[]
  brief: TrendBrief | null
}
export type Run = {
  id: number
  kind: string
  trigger: string
  source_key: string | null
  status: string
  started_at: string
  finished_at: string | null
  fetched: number
  new: number
  duplicates: number
  rejected_prefilter: number
  rejected_ai: number
  processed: number
  failed: number
  cost_usd_estimate: number
  stop_reason: string | null
  error: string | null
}
export type Stats = {
  funnel: Record<'fetched' | 'new' | 'rejected_prefilter' | 'rejected_ai' | 'duplicate' | 'failed' | 'processed', number>
  by_category: { slug: string; name: string; items: number; avg_quality: number | null }[]
  by_content_type: { key: string; items: number }[]
  by_source: { key: string; name: string; items: number; processed: number }[]
  per_day: { date: string; items: number }[]
  pipeline_runs: Run[]
  ai_cost: { classifier_usd: number; classifier_today_usd: number; trend_brief_usd: number; total_usd: number }
}

export type Health = { status: 'ok' | 'degraded'; db: 'ok' | 'error'; version: string }

/** The API's error envelope as an exception. `status` 0 means the request never got a response. */
export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export type Params = Record<string, string | number | undefined | null>

export function qs(params: Params = {}): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${V1}${path}`, init)
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the NewsDC API.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.error?.code ?? 'http_error', body?.error?.message ?? `HTTP ${res.status}`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const postJson = (body: unknown, extra: RequestInit = {}): RequestInit => ({
  method: 'POST',
  ...extra,
  headers: { 'Content-Type': 'application/json', ...extra.headers },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/health'),
  items: (p: Params) => request<Page<ItemSummary>>(`/items${qs(p)}`),
  item: (id: number) => request<ItemDetail>(`/items/${id}`),
  related: (id: number) => request<RelatedItem[]>(`/items/${id}/related`),
  trending: (p: Params) => request<Page<ItemSummary>>(`/feeds/trending${qs(p)}`),
  relevant: (p: Params) => request<Page<ItemSummary>>(`/feeds/relevant${qs(p)}`),
  forYou: (profile: unknown, p: Params) => request<ForYouPage>(`/feeds/foryou${qs(p)}`, postJson(profile)),
  topics: () => request<TopicSummary[]>('/topics'),
  topic: (slug: string, p: Params) => request<TopicPage>(`/topics/${encodeURIComponent(slug)}${qs(p)}`),
  search: (p: Params) => request<SearchPage>(`/search${qs(p)}`),
  suggestions: () => request<string[]>('/ask/suggestions'),
  trends: () => request<Trends>('/trends'),
  stats: () => request<Stats>('/stats'),
  exportUrl: (format: 'json' | 'md', p: Params = {}) => `${V1}/export${qs({ ...p, format })}`,
}

// --- Admin (cookie session + CSRF header, docs/API.md#admin) ----------------------------------

export type AdminSession = { csrf_token: string; expires_at: string }
export type AdminSource = {
  key: string
  name: string
  type: string
  url: string
  enabled: boolean
  admin_disabled: boolean
  active: boolean
  terms_url: string | null
  last_fetched_at: string | null
  last_success_at: string | null
  last_status: string | null
  last_error: string | null
}
export type AdminCategory = {
  slug: string
  name: string
  description: string
  keywords: string[]
  enabled: boolean
  sort_order: number
  admin_edited_at: string | null
}
export type AdminJob = {
  id: number
  kind: string
  payload: Record<string, unknown>
  status: string
  attempt_count: number
  max_attempts: number
  next_retry_at: string | null
  last_error: string | null
  created_at: string
  finished_at: string | null
}
export type RejectedItem = {
  id: number
  title: string
  url: string
  publisher: string | null
  published_at: string | null
  status: string
  reason: string | null
  relevance_score: number | null
  quality_score: number | null
  duplicate_of: number | null
  duplicate_similarity: number | null
  updated_at: string
}

const cred: RequestInit = { credentials: 'include' }

export const admin = {
  login: (token: string) => request<AdminSession>('/admin/login', postJson({ token }, cred)),
  session: () => request<AdminSession>('/admin/session', cred),
  get: <T>(path: string) => request<T>(`/admin${path}`, cred),
  /** POST/PATCH need the CSRF token from login/session. */
  send: <T>(csrf: string, method: 'POST' | 'PATCH', path: string, body: unknown = {}) =>
    request<T>(`/admin${path}`, { ...postJson(body, { ...cred, headers: { 'X-CSRF-Token': csrf } }), method }),
}

// --- Ask NewsDC (SSE over a POST body, docs/API.md#ask-newsdc-phase-6) -------------------------

export type AskEvent =
  | { event: 'sources'; data: { sources: AskSource[] } }
  | { event: 'status'; data: { stage: string } }
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: { cited: number[]; removed_citations: number; truncated: boolean } }
  | { event: 'error'; data: { code: string; message: string } }

/** Split a growing SSE buffer into complete events; returns them plus the unfinished remainder. */
export function parseSse(buffer: string): { events: AskEvent[]; rest: string } {
  const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = parts.pop() ?? ''
  const events: AskEvent[] = []
  for (const block of parts) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length) events.push({ event, data: JSON.parse(data.join('\n')) } as AskEvent)
  }
  return { events, rest }
}

export type ChatMessage = { role: 'user' | 'assistant'; content: string }

export async function* ask(question: string, history: ChatMessage[], signal: AbortSignal): AsyncGenerator<AskEvent> {
  let res: Response
  try {
    res = await fetch(`${V1}/ask`, { ...postJson({ question, history }), signal })
  } catch (e) {
    if (signal.aborted) throw e
    throw new ApiError(0, 'network_error', 'Could not reach the NewsDC API.')
  }
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.error?.code ?? 'http_error', body?.error?.message ?? `HTTP ${res.status}`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseSse(buffer + value)
    buffer = parsed.rest
    yield* parsed.events
  }
}
