import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowUp, ArrowUpRight, MessageCircleQuestion, Quote, RotateCw, Search, ShieldCheck, Sparkles, Square } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { Markdown } from '@/components/Markdown'
import { Skeleton, TypeBadge, WithAside } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ApiError, api, ask, type AskSource, type ChatMessage } from '@/lib/api'
import { fmtDate, safeUrl, useTitle } from '@/lib/format'
import { cn } from '@/lib/utils'

type Turn = {
  question: string
  answer: string
  sources: AskSource[]
  status: 'retrieving' | 'generating' | 'done' | 'error' | 'stopped'
  error?: string
  truncated?: boolean
}

const MAX_HISTORY_TURNS = 2 // the API takes at most 4 messages (2 exchanges)

function Sources({ sources, turn }: { sources: AskSource[]; turn: number }) {
  if (!sources.length) return null
  return (
    <div className="mt-4">
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sources ({sources.length})</h3>
      <ol className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3" aria-label="Sources">
        {sources.map((s) => (
          <li key={s.n} id={`src-${turn}-${s.n}`} className="scroll-mt-24 rounded-xl border bg-surface p-3 text-xs shadow-card transition target:border-primary target:ring-2 target:ring-primary/40">
            <div className="flex items-start gap-2.5">
              <span className="grid size-6 shrink-0 place-items-center rounded-md bg-primary/12 text-xs font-bold text-primary-ink">{s.n}</span>
              <div className="min-w-0">
                <a href={safeUrl(s.url)} target="_blank" rel="noopener noreferrer" className="line-clamp-2 text-sm leading-snug font-medium hover:underline">
                  {s.title}
                </a>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-muted-foreground">
                  {s.publisher} · {fmtDate(s.published_at)} <TypeBadge type={s.content_type} />
                </p>
                <Link to={`/article/${s.id}`} className="mt-1 inline-block font-medium text-primary-ink hover:underline">
                  NewsDC summary →
                </Link>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Three pulsing dots plus a label: the retrieval and writing states. */
function Working({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((d) => (
          <span key={d} className="size-1.5 animate-pulse rounded-full bg-ai" style={{ animationDelay: `${d}ms` }} />
        ))}
      </span>
      {label}
    </p>
  )
}

function AiAvatar() {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-ai text-ai-foreground" aria-hidden>
      <Sparkles className="size-4" />
    </span>
  )
}

const HOW = [
  [Search, 'Finds the most relevant collected articles (keywords + meaning).'],
  [Quote, 'Writes an answer only from those articles, citing each claim as [n].'],
  [ShieldCheck, 'Drops any citation that does not match a retrieved source.'],
] as const

export default function AskPage() {
  useTitle('Ask NewsDC', 'Ask questions about data center news and get answers that cite their sources.')
  const suggestions = useQuery({ queryKey: ['suggestions'], queryFn: api.suggestions, staleTime: Infinity })
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const abort = useRef<AbortController | null>(null)
  const busy = turns.at(-1)?.status === 'retrieving' || turns.at(-1)?.status === 'generating'
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => inputRef.current?.focus(), [])

  const update = (patch: (t: Turn) => Partial<Turn>) =>
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, ...patch(t) } : t)))

  async function send(question: string) {
    question = question.trim()
    if (question.length < 3 || busy) return
    const history: ChatMessage[] = turns
      .filter((t) => t.status === 'done' && t.answer)
      .slice(-MAX_HISTORY_TURNS)
      .flatMap((t) => [
        { role: 'user' as const, content: t.question.slice(0, 4000) },
        { role: 'assistant' as const, content: t.answer.slice(0, 4000) },
      ])
    setTurns((ts) => [...ts, { question, answer: '', sources: [], status: 'retrieving' }])
    setInput('')
    const ctrl = new AbortController()
    abort.current = ctrl
    try {
      for await (const ev of ask(question, history, ctrl.signal)) {
        if (ev.event === 'sources') update(() => ({ sources: ev.data.sources }))
        else if (ev.event === 'status') update(() => ({ status: 'generating' }))
        else if (ev.event === 'token') update((t) => ({ answer: t.answer + ev.data.text }))
        else if (ev.event === 'done') update(() => ({ status: 'done', truncated: ev.data.truncated }))
        // The API says: discard tokens already shown when an error arrives.
        else if (ev.event === 'error') update(() => ({ status: 'error', answer: '', error: ev.data.message }))
      }
      update((t) => (t.status === 'generating' || t.status === 'retrieving' ? { status: 'error', answer: '', error: 'The answer was cut off. Ask again.' } : {}))
    } catch (e) {
      if (ctrl.signal.aborted) update(() => ({ status: 'stopped' }))
      else
        update(() => ({
          status: 'error',
          answer: '',
          error:
            e instanceof ApiError
              ? e.status === 429
                ? 'You asked a lot of questions in a short time. Wait a minute and try again.'
                : e.status === 503
                  ? 'The assistant is not configured on this server.'
                  : e.message
              : 'Something went wrong.',
        }))
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  const empty = turns.length === 0
  return (
    <WithAside
      label="About Ask NewsDC"
      aside={
        <section aria-labelledby="how-title" className="rounded-2xl border bg-surface p-4 shadow-card">
          <h2 id="how-title" className="mb-3 flex items-center gap-2 font-semibold">
            <Sparkles className="size-4 text-ai" aria-hidden /> How answers work
          </h2>
          <ol className="space-y-3 text-sm">
            {HOW.map(([Icon, text], i) => (
              <li key={i} className="flex gap-3">
                <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-ai/12 text-ai-ink" aria-hidden>
                  <Icon className="size-4" />
                </span>
                <span className="text-muted-foreground">{text}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 rounded-lg bg-elevated p-3 text-xs text-muted-foreground">Answers can still be wrong. Open the sources before you rely on one.</p>
        </section>
      }
    >
      <div className="mx-auto flex min-h-[calc(100dvh-4rem-4.25rem-2.5rem-env(safe-area-inset-bottom))] max-w-3xl flex-col md:min-h-[calc(100dvh-4rem-3rem)] 3xl:max-w-4xl">
        {empty ? (
          <section aria-labelledby="ask-title" className="flex flex-1 flex-col justify-center py-6 text-center">
            <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-ai text-ai-foreground shadow-raised" aria-hidden>
              <Sparkles className="size-7" />
            </span>
            <h1 id="ask-title" className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">
              Ask NewsDC
            </h1>
            <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
              Answers come only from articles NewsDC has collected, with numbered citations. They can still be wrong: check the sources.
            </p>
            <h2 id="try-title" className="mt-8 mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Try asking
            </h2>
            {suggestions.isPending ? (
              <Skeleton className="mx-auto h-40 w-full" />
            ) : (
              <ul aria-labelledby="try-title" className="grid gap-2 text-left sm:grid-cols-2">
                {(suggestions.data ?? []).map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      onClick={() => void send(s)}
                      className="group flex h-full w-full items-start gap-3 rounded-xl border bg-surface p-3 text-left text-sm shadow-card transition-colors hover:border-ai/50 hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-ai" aria-hidden />
                      <span className="flex-1">{s}</span>
                      <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition group-hover:text-foreground" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : (
          <h1 className="sr-only">Ask NewsDC</h1>
        )}

        <div className={cn('space-y-8', !empty && 'flex-1 pt-2')} aria-live="polite" aria-busy={busy}>
          {turns.map((t, i) => (
            <section key={i} aria-label={`Question ${i + 1}`}>
              <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md border border-primary/25 bg-primary/12 px-4 py-2.5 text-sm text-foreground">{t.question}</p>
              <div className="mt-4 flex gap-3">
                <AiAvatar />
                <div className="min-w-0 flex-1">
                  <p className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-semibold text-foreground">NewsDC AI</span>
                    {t.status === 'done' && <Badge variant="ai">AI-generated · {t.sources.length} sources</Badge>}
                  </p>
                  {t.status === 'retrieving' && <Working label="Searching collected articles…" />}
                  {t.status === 'generating' && !t.answer && <Working label="Writing an answer…" />}
                  {t.status === 'error' && (
                    <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm">
                      <p className="flex items-start gap-2 text-destructive-ink">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {t.error}
                      </p>
                      <Button variant="outline" size="sm" className="mt-3" disabled={busy} onClick={() => void send(t.question)}>
                        <RotateCw /> Ask again
                      </Button>
                    </div>
                  )}
                  {t.answer && (
                    <div className={cn(t.status === 'generating' && '[&_.prose-news>*:last-child]:after:ml-0.5 [&_.prose-news>*:last-child]:after:inline-block [&_.prose-news>*:last-child]:after:h-4 [&_.prose-news>*:last-child]:after:w-1.5 [&_.prose-news>*:last-child]:after:animate-pulse [&_.prose-news>*:last-child]:after:bg-ai [&_.prose-news>*:last-child]:after:align-middle [&_.prose-news>*:last-child]:after:content-[""]')}>
                      <Markdown text={t.answer} known={new Set(t.sources.map((s) => s.n))} idPrefix={`src-${i}`} />
                    </div>
                  )}
                  {t.status === 'stopped' && <p className="mt-1 text-xs text-muted-foreground">Stopped.</p>}
                  {t.truncated && <p className="mt-1 text-xs text-muted-foreground">The answer reached its length limit.</p>}
                  {t.status === 'retrieving' && (
                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      <Skeleton className="h-20 rounded-xl" />
                      <Skeleton className="h-20 rounded-xl" />
                    </div>
                  )}
                  {t.status !== 'error' && <Sources sources={t.sources} turn={i} />}
                </div>
              </div>
            </section>
          ))}
        </div>

        <div className="sticky bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-20 mt-6 bg-gradient-to-t from-background via-background to-background/0 pt-3 pb-2 md:bottom-0 md:pb-4">
          <form onSubmit={submit} className="flex items-end gap-2 rounded-2xl border bg-surface p-2 shadow-raised focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30">
            <label htmlFor="ask-input" className="sr-only">
              Your question
            </label>
            <textarea
              id="ask-input"
              ref={inputRef}
              rows={2}
              value={input}
              maxLength={500}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(input)
                }
              }}
              placeholder={empty ? 'Ask about data center news…' : 'Ask a follow-up…'}
              className="min-h-11 flex-1 resize-none bg-transparent px-2 py-1.5 text-base outline-none placeholder:text-muted-foreground md:text-sm"
            />
            {busy ? (
              <Button type="button" size="icon" variant="outline" aria-label="Stop" onClick={() => abort.current?.abort()}>
                <Square />
              </Button>
            ) : (
              <Button type="submit" size="icon" variant="ai" aria-label="Ask" disabled={input.trim().length < 3}>
                <ArrowUp />
              </Button>
            )}
          </form>
          <p className="mt-1 flex justify-between px-1 text-2xs text-muted-foreground">
            <span className="max-sm:hidden">Enter to send · Shift + Enter for a new line</span>
            <span className={cn('ml-auto', input.length < 450 && 'invisible')}>{input.length}/500</span>
          </p>
        </div>
      </div>
    </WithAside>
  )
}
