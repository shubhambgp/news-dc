import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { Markdown } from '@/components/Markdown'
import { PageHeader, TypeBadge } from '@/components/common'
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
    <ol className="mt-3 grid gap-2 sm:grid-cols-2" aria-label="Sources">
      {sources.map((s) => (
        <li key={s.n} id={`src-${turn}-${s.n}`} className="scroll-mt-20 rounded-md border bg-card p-2 text-xs target:ring-2 target:ring-primary">
          <div className="flex items-start gap-2">
            <span className="rounded bg-primary/10 px-1.5 font-semibold text-primary">{s.n}</span>
            <div className="min-w-0">
              <a href={safeUrl(s.url)} target="_blank" rel="noopener noreferrer" className="line-clamp-2 font-medium hover:underline">
                {s.title}
              </a>
              <p className="mt-0.5 flex flex-wrap items-center gap-1 text-muted-foreground">
                {s.publisher} · {fmtDate(s.published_at)} <TypeBadge type={s.content_type} />
              </p>
              <Link to={`/article/${s.id}`} className="text-primary hover:underline">
                NewsDC summary
              </Link>
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

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

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <PageHeader title="Ask NewsDC" />
      <p className="-mt-2 mb-4 text-sm text-muted-foreground">
        Answers come only from articles NewsDC has collected, with numbered citations. They can still be wrong: check the sources.
      </p>

      {turns.length === 0 && (
        <section aria-labelledby="try-title" className="mb-4">
          <h2 id="try-title" className="mb-2 text-sm font-semibold">
            Try asking
          </h2>
          <ul className="flex flex-wrap gap-2">
            {(suggestions.data ?? []).map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => void send(s)}
                  className="rounded-full border px-3 py-1.5 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="space-y-8" aria-live="polite" aria-busy={busy}>
        {turns.map((t, i) => (
          <section key={i} aria-label={`Question ${i + 1}`}>
            <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">{t.question}</p>
            <div className="mt-3">
              {t.status === 'retrieving' && <p className="text-sm text-muted-foreground">Searching collected articles…</p>}
              {t.status === 'generating' && !t.answer && <p className="text-sm text-muted-foreground">Writing an answer…</p>}
              {t.status === 'error' && (
                <p role="alert" className="text-sm text-destructive">
                  {t.error}
                </p>
              )}
              {t.answer && <Markdown text={t.answer} known={new Set(t.sources.map((s) => s.n))} idPrefix={`src-${i}`} />}
              {t.status === 'stopped' && <p className="mt-1 text-xs text-muted-foreground">Stopped.</p>}
              {t.truncated && <p className="mt-1 text-xs text-muted-foreground">The answer reached its length limit.</p>}
              {t.status !== 'error' && <Sources sources={t.sources} turn={i} />}
            </div>
          </section>
        ))}
      </div>

      <form onSubmit={submit} className="sticky bottom-16 mt-6 flex items-end gap-2 rounded-lg border bg-background p-2 shadow-sm lg:bottom-4">
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
          placeholder="Ask about data center news…"
          className="min-h-10 flex-1 resize-none bg-transparent px-1 text-sm outline-none"
        />
        {busy ? (
          <Button type="button" size="icon" variant="outline" aria-label="Stop" onClick={() => abort.current?.abort()}>
            <Square />
          </Button>
        ) : (
          <Button type="submit" size="icon" aria-label="Ask" disabled={input.trim().length < 3}>
            <ArrowUp />
          </Button>
        )}
      </form>
      <p className={cn('mt-1 text-right text-[11px] text-muted-foreground', input.length < 450 && 'invisible')}>{input.length}/500</p>
    </div>
  )
}
