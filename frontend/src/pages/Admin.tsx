import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Database, FileText, Layers, ListChecks, LogOut, Pencil, Play, RefreshCw, ShieldCheck, Sparkles, Workflow } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'

import { ErrorState, ListSkeleton, PageHeader, StatTile, StatusBadge } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  ApiError,
  admin,
  type AdminCategory,
  type AdminJob,
  type AdminSession,
  type AdminSource,
  type Page,
  type RejectedItem,
  type Run,
} from '@/lib/api'
import { fmtUsd, safeUrl, timeAgo, useTitle } from '@/lib/format'
import { cn } from '@/lib/utils'

function Login({ onLogin }: { onLogin: (s: AdminSession) => void }) {
  const [token, setToken] = useState('')
  const login = useMutation({ mutationFn: admin.login, onSuccess: onLogin })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (token) login.mutate(token)
  }
  return (
    <form onSubmit={submit} className="mx-auto mt-6 max-w-sm space-y-4 rounded-2xl border bg-surface p-6 shadow-raised">
      <span className="grid size-11 place-items-center rounded-xl bg-primary/12 text-primary" aria-hidden>
        <ShieldCheck className="size-5" />
      </span>
      <div>
        <h2 className="text-lg font-semibold">Admin sign in</h2>
        <p className="text-sm text-muted-foreground">Use the server's admin token. The session lives in an HTTP-only cookie.</p>
      </div>
      <label className="block text-sm font-medium">
        Admin token
        <Input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} className="mt-1.5" />
      </label>
      {login.isError && (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-2.5 text-sm text-destructive-ink">
          {login.error instanceof ApiError && login.error.status === 401
            ? 'Wrong token.'
            : login.error instanceof ApiError && login.error.status === 429
              ? 'Too many attempts. Wait a minute.'
              : login.error.message}
        </p>
      )}
      <Button type="submit" disabled={!token || login.isPending} className="w-full">
        {login.isPending ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  )
}

function Section({ title, icon: Icon, children, action }: { title: string; icon: typeof Database; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="min-w-0 rounded-2xl border bg-surface p-4 shadow-card sm:p-5" aria-label={title}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <Icon className="size-4 text-muted-foreground" aria-hidden /> {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    // Scrolls inside its own box on small screens; the header row stays visible while it scrolls.
    <div className="relative max-h-[32rem] overflow-auto rounded-xl border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-elevated text-left text-xs text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:px-3 [&_td]:py-2 [&_td]:align-middle [&_tr]:border-t [&_tr:hover]:bg-elevated/50">{children}</tbody>
      </table>
    </div>
  )
}

function CategoryRow({ c, save }: { c: AdminCategory; save: (slug: string, body: Partial<AdminCategory>) => void }) {
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({ name: c.name, description: c.description, keywords: c.keywords.join(', ') })
  if (edit)
    return (
      <tr>
        <td colSpan={4}>
          <form
            className="grid gap-2 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault()
              save(c.slug, {
                name: form.name,
                description: form.description,
                keywords: form.keywords.split(',').map((k) => k.trim()).filter(Boolean),
              })
              setEdit(false)
            }}
          >
            <label className="text-xs">
              Name
              <Input className="mt-1" value={form.name} maxLength={80} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-xs">
              Keywords (comma separated)
              <Input className="mt-1" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
            </label>
            <label className="text-xs sm:col-span-2">
              Description
              <Textarea className="mt-1" value={form.description} maxLength={500} required onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <div className="flex gap-2">
              <Button size="sm" type="submit">Save</Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setEdit(false)}>Cancel</Button>
            </div>
            <p className="text-xs text-muted-foreground sm:col-span-2">Existing items become "outdated"; reclassify them with Reprocess outdated (paid).</p>
          </form>
        </td>
      </tr>
    )
  return (
    <tr>
      <td className="font-medium">{c.name}{c.admin_edited_at && <span className="ml-1 text-muted-foreground">(edited)</span>}</td>
      <td className="max-w-xs truncate text-muted-foreground" title={c.description}>{c.description}</td>
      <td>
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={c.enabled} onChange={(e) => save(c.slug, { enabled: e.target.checked })} />
          <span className="sr-only">Enabled: {c.name}</span>
          <Badge variant={c.enabled ? 'success' : 'neutral'}>{c.enabled ? 'on' : 'off'}</Badge>
        </label>
      </td>
      <td>
        <Button size="icon" variant="ghost" aria-label={`Edit ${c.name}`} onClick={() => setEdit(true)}>
          <Pencil />
        </Button>
      </td>
    </tr>
  )
}

/** Source state as a dot plus words (never colour alone). */
function SourceHealth({ s }: { s: AdminSource }) {
  const [label, dot] = !s.enabled
    ? ['Disabled in config', 'bg-muted-foreground']
    : s.admin_disabled
      ? ['Paused', 'bg-warning']
      : s.last_error
        ? ['Active · last fetch failed', 'bg-destructive']
        : ['Active', 'bg-success']
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className={cn('size-2 rounded-full', dot)} aria-hidden />
      {label}
    </span>
  )
}

function Dashboard({ session, onLogout }: { session: AdminSession; onLogout: () => void }) {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [rejPage, setRejPage] = useState(1)
  const [jobFilter, setJobFilter] = useState('')
  const [rejStatus, setRejStatus] = useState('')
  const sources = useQuery({ queryKey: ['admin', 'sources'], queryFn: () => admin.get<AdminSource[]>('/sources') })
  const categories = useQuery({ queryKey: ['admin', 'categories'], queryFn: () => admin.get<AdminCategory[]>('/categories') })
  const jobs = useQuery({ queryKey: ['admin', 'jobs'], queryFn: () => admin.get<AdminJob[]>('/jobs'), refetchInterval: 10_000 })
  const runs = useQuery({ queryKey: ['admin', 'runs'], queryFn: () => admin.get<Run[]>('/runs') })
  const rejected = useQuery({
    queryKey: ['admin', 'rejected', rejPage, rejStatus],
    queryFn: () => admin.get<Page<RejectedItem>>(`/rejected?page=${rejPage}&page_size=20${rejStatus ? `&status=${rejStatus}` : ''}`),
  })

  const act = useMutation({
    mutationFn: ({ method = 'POST', path, body }: { method?: 'POST' | 'PATCH'; path: string; body?: unknown; label: string }) =>
      admin.send<{ job_id?: number | null; items?: number }>(session.csrf_token, method, path, body),
    onSuccess: (r, v) => {
      const job = r && 'job_id' in r ? (r.job_id ? ` Job #${r.job_id} queued.` : ' A job of this kind is already queued; it will pick this up.') : ''
      const items = r && typeof r.items === 'number' ? ` ${r.items} item(s) sent back to the pipeline.` : ''
      setMsg({ ok: true, text: `${v.label}: done.${items}${job}` })
      qc.invalidateQueries({ queryKey: ['admin'] })
    },
    onError: (e, v) => {
      if (e instanceof ApiError && e.status === 401) onLogout()
      setMsg({ ok: false, text: `${v.label}: ${e.message}` })
    },
  })
  const run = (label: string, path: string, body?: unknown, method?: 'POST' | 'PATCH') => {
    if (/pipeline|reprocess/i.test(path) && !window.confirm(`${label} makes paid LLM calls. Continue?`)) return
    act.mutate({ label, path, body, method })
  }

  const logout = async () => {
    await admin.send(session.csrf_token, 'POST', '/logout').catch(() => undefined)
    onLogout()
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatTile icon={Database} label="Active sources" value={sources.data ? `${sources.data.filter((x) => x.active).length}/${sources.data.length}` : '…'} sub={sources.data ? `${sources.data.filter((x) => x.last_error).length} with a fetch error` : undefined} tone="data" />
        <StatTile icon={Workflow} label="Jobs queued or running" value={jobs.data ? jobs.data.filter((j) => ['pending', 'running', 'retry_wait'].includes(j.status)).length : '…'} sub="Refreshes every 10 s" />
        <StatTile icon={AlertTriangle} label="Dead letters" value={jobs.data ? jobs.data.filter((j) => j.status === 'dead_letter').length : '…'} sub="Jobs that ran out of retries" tone="ai" />
        <StatTile icon={ListChecks} label="Kept out of the feed" value={rejected.data && !rejStatus ? rejected.data.total.toLocaleString() : '…'} sub="Rejected by prefilter or AI, or duplicates" tone="success" />
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border bg-surface p-3 shadow-card">
        <Button size="sm" disabled={act.isPending} onClick={() => run('Ingest all sources', '/ingest', {})}>
          <Play /> Ingest all sources
        </Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Run pipeline', '/pipeline')}>
          <Sparkles /> Run pipeline <Badge variant="warning">paid</Badge>
        </Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Regenerate trend brief', '/trend-brief')}>
          <FileText /> Regenerate trend brief <Badge variant="warning">paid</Badge>
        </Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Reprocess outdated', '/reprocess-outdated')}>
          <RefreshCw /> Reprocess outdated <Badge variant="warning">paid</Badge>
        </Button>
        <span className="text-xs text-muted-foreground max-lg:basis-full lg:ml-auto">Session expires {timeAgo(session.expires_at)} · actions queue jobs for the worker</span>
        <Button size="sm" variant="ghost" onClick={logout}>
          <LogOut /> Log out
        </Button>
      </div>
      {msg && (
        <p
          role="status"
          className={cn('flex items-start gap-2 rounded-xl border p-3 text-sm', msg.ok ? 'border-success/40 bg-success/10 text-success-ink' : 'border-destructive/40 bg-destructive/10 text-destructive-ink')}
        >
          {msg.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />}
          {msg.text}
        </p>
      )}

      <Section title="Sources" icon={Database}>
        {sources.isPending ? <ListSkeleton rows={3} /> : sources.isError ? <ErrorState error={sources.error} retry={() => sources.refetch()} /> : (
          <Table head={['Source', 'State', 'Last fetch', 'Last status', '']}>
            {sources.data.map((s) => (
              <tr key={s.key}>
                <td>
                  <span className="font-medium">{s.name}</span> <span className="text-xs text-muted-foreground">({s.key})</span>
                </td>
                <td className="whitespace-nowrap">
                  <SourceHealth s={s} />
                </td>
                <td className="whitespace-nowrap text-muted-foreground">{timeAgo(s.last_fetched_at)}</td>
                <td className={cn('max-w-xs truncate', s.last_error && 'text-destructive-ink')} title={s.last_error ?? undefined}>
                  {s.last_status ?? '–'}
                </td>
                <td className="whitespace-nowrap">
                  {s.enabled && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => run(`${s.active ? 'Pause' : 'Resume'} ${s.key}`, `/sources/${s.key}`, { active: !s.active }, 'PATCH')}>
                        {s.active ? 'Pause' : 'Resume'}
                      </Button>
                      {s.active && <Button size="sm" variant="ghost" onClick={() => run(`Ingest ${s.key}`, '/ingest', { source: s.key })}>Ingest</Button>}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Categories" icon={Layers}>
        {categories.isPending ? <ListSkeleton rows={3} /> : categories.isError ? <ErrorState error={categories.error} retry={() => categories.refetch()} /> : (
          <Table head={['Name', 'Description', 'Enabled', '']}>
            {categories.data.map((c) => (
              <CategoryRow key={c.slug} c={c} save={(slug, body) => run(`Update ${slug}`, `/categories/${slug}`, body, 'PATCH')} />
            ))}
          </Table>
        )}
      </Section>

      <Section
        title="Jobs"
        icon={Workflow}
        action={
          <Select aria-label="Job status" className="w-auto" value={jobFilter} onChange={(e) => setJobFilter(e.target.value)}>
            <option value="">All statuses</option>
            {['pending', 'running', 'retry_wait', 'succeeded', 'dead_letter', 'cancelled'].map((x) => (
              <option key={x} value={x}>
                {x.replace(/_/g, ' ')}
              </option>
            ))}
          </Select>
        }
      >
        {jobs.isPending ? <ListSkeleton rows={3} /> : jobs.isError ? <ErrorState error={jobs.error} retry={() => jobs.refetch()} /> : (
          <Table head={['#', 'Kind', 'Status', 'Attempts', 'Created', 'Last error', '']}>
            {jobs.data.filter((j) => !jobFilter || j.status === jobFilter).map((j) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>{j.kind}{typeof j.payload.source === 'string' && ` · ${j.payload.source}`}</td>
                <td>
                  <StatusBadge status={j.status} />
                </td>
                <td className="tabular-nums">{j.attempt_count}/{j.max_attempts}</td>
                <td>{timeAgo(j.created_at)}</td>
                <td className="max-w-xs truncate" title={j.last_error ?? undefined}>{j.last_error ?? ''}</td>
                <td>{j.status === 'dead_letter' && <Button size="sm" variant="ghost" onClick={() => run(`Retry job ${j.id}`, `/jobs/${j.id}/retry`)}>Retry</Button>}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Runs" icon={Play}>
        {runs.isPending ? <ListSkeleton rows={3} /> : runs.isError ? <ErrorState error={runs.error} retry={() => runs.refetch()} /> : (
          <Table head={['#', 'Kind', 'Started', 'Status', 'Fetched', 'New', 'Published', 'Rejected', 'Cost', 'Note']}>
            {runs.data.slice(0, 20).map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.kind}{r.source_key && ` · ${r.source_key}`} <span className="text-muted-foreground">({r.trigger})</span></td>
                <td>{timeAgo(r.started_at)}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td className="tabular-nums">{r.fetched}</td>
                <td className="tabular-nums">{r.new}</td>
                <td className="tabular-nums">{r.processed}</td>
                <td className="tabular-nums">{r.rejected_prefilter + r.rejected_ai}</td>
                <td className="tabular-nums">{fmtUsd(r.cost_usd_estimate)}</td>
                <td className="max-w-xs truncate" title={r.error ?? r.stop_reason ?? undefined}>{r.error ?? r.stop_reason ?? ''}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section
        title={`Kept out of the feed${rejected.data ? ` (${rejected.data.total})` : ''}`}
        icon={ListChecks}
        action={
          <div className="flex flex-wrap items-center gap-1">
            <Select
              aria-label="Reason"
              className="w-auto"
              value={rejStatus}
              onChange={(e) => {
                setRejStatus(e.target.value)
                setRejPage(1)
              }}
            >
              <option value="">All reasons</option>
              <option value="rejected_prefilter">Rejected (prefilter)</option>
              <option value="rejected_ai">Rejected (AI)</option>
              <option value="duplicate">Duplicate</option>
            </Select>
            <Button size="sm" variant="ghost" disabled={rejPage === 1} onClick={() => setRejPage((p) => p - 1)}>Previous</Button>
            <Button size="sm" variant="ghost" disabled={!rejected.data?.has_more} onClick={() => setRejPage((p) => p + 1)}>Next</Button>
          </div>
        }
      >
        {rejected.isPending ? <ListSkeleton rows={3} /> : rejected.isError ? <ErrorState error={rejected.error} retry={() => rejected.refetch()} /> : (
          <Table head={['Title', 'Status', 'Reason', 'Rel.', 'Qual.', '']}>
            {rejected.data.items.map((r) => (
              <tr key={r.id}>
                <td className="max-w-sm">
                  <a href={safeUrl(r.url)} target="_blank" rel="noopener noreferrer" className="line-clamp-1 hover:underline">{r.title}</a>
                </td>
                <td className="whitespace-nowrap">
                  <Badge variant={r.status === 'duplicate' ? 'neutral' : 'warning'}>{r.status.replace(/_/g, ' ')}</Badge>
                </td>
                <td className="max-w-xs truncate" title={r.reason ?? undefined}>{r.reason ?? ''}</td>
                <td className="tabular-nums">{r.relevance_score ?? '–'}</td>
                <td className="tabular-nums">{r.quality_score ?? '–'}</td>
                <td><Button size="sm" variant="ghost" onClick={() => run(`Reprocess item ${r.id}`, `/items/${r.id}/reprocess`)}>Reprocess</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  )
}

export default function AdminPage() {
  useTitle('Admin')
  const qc = useQueryClient()
  const session = useQuery({ queryKey: ['admin-session'], queryFn: admin.session, retry: false })
  const setSession = (s: AdminSession | null) => {
    qc.setQueryData(['admin-session'], s)
    if (!s) qc.removeQueries({ queryKey: ['admin'] })
  }

  let body: ReactNode
  if (session.isPending) body = <ListSkeleton rows={3} />
  else if (session.data) body = <Dashboard session={session.data} onLogout={() => setSession(null)} />
  else if (session.error instanceof ApiError && session.error.code === 'admin_disabled')
    body = <ErrorState error={new ApiError(503, 'admin_disabled', 'Admin is disabled on this server (ADMIN_TOKEN and SESSION_SECRET are not set).')} />
  else if (!session.error || (session.error instanceof ApiError && session.error.status === 401)) body = <Login onLogin={setSession} />
  else body = <ErrorState error={session.error} retry={() => session.refetch()} />

  return (
    <>
      <PageHeader title="Admin" icon={ShieldCheck} description="Sources, categories, jobs, runs and the items the pipeline kept out of the feed." />
      {body}
    </>
  )
}
