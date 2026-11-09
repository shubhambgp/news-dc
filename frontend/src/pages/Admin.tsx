import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LogOut, Pencil } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'

import { ErrorState, ListSkeleton, PageHeader } from '@/components/common'
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

const inputCls = 'h-9 w-full rounded-md border bg-background px-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'

function Login({ onLogin }: { onLogin: (s: AdminSession) => void }) {
  const [token, setToken] = useState('')
  const login = useMutation({ mutationFn: admin.login, onSuccess: onLogin })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (token) login.mutate(token)
  }
  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-3 rounded-lg border bg-card p-5">
      <h2 className="font-semibold">Admin login</h2>
      <label className="block text-sm">
        Admin token
        <input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} className={`${inputCls} mt-1`} />
      </label>
      {login.isError && (
        <p role="alert" className="text-sm text-destructive">
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

function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-4" aria-label={title}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-left text-muted-foreground">
          <tr>
            {head.map((h) => (
              <th key={h} className="py-1 pr-3 font-normal whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:py-1.5 [&_td]:pr-3 [&_tr]:border-t">{children}</tbody>
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
              <input className={inputCls} value={form.name} maxLength={80} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-xs">
              Keywords (comma separated)
              <input className={inputCls} value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
            </label>
            <label className="text-xs sm:col-span-2">
              Description
              <textarea className={`${inputCls} h-16 py-1`} value={form.description} maxLength={500} required onChange={(e) => setForm({ ...form, description: e.target.value })} />
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
        <label className="inline-flex items-center gap-1">
          <input type="checkbox" checked={c.enabled} onChange={(e) => save(c.slug, { enabled: e.target.checked })} />
          <span className="sr-only">Enabled: {c.name}</span>
          {c.enabled ? 'on' : 'off'}
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

function Dashboard({ session, onLogout }: { session: AdminSession; onLogout: () => void }) {
  const qc = useQueryClient()
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [rejPage, setRejPage] = useState(1)
  const sources = useQuery({ queryKey: ['admin', 'sources'], queryFn: () => admin.get<AdminSource[]>('/sources') })
  const categories = useQuery({ queryKey: ['admin', 'categories'], queryFn: () => admin.get<AdminCategory[]>('/categories') })
  const jobs = useQuery({ queryKey: ['admin', 'jobs'], queryFn: () => admin.get<AdminJob[]>('/jobs'), refetchInterval: 10_000 })
  const runs = useQuery({ queryKey: ['admin', 'runs'], queryFn: () => admin.get<Run[]>('/runs') })
  const rejected = useQuery({
    queryKey: ['admin', 'rejected', rejPage],
    queryFn: () => admin.get<Page<RejectedItem>>(`/rejected?page=${rejPage}&page_size=20`),
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
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={act.isPending} onClick={() => run('Ingest all sources', '/ingest', {})}>Ingest all sources</Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Run pipeline', '/pipeline')}>Run pipeline</Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Regenerate trend brief', '/trend-brief')}>Regenerate trend brief</Button>
        <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => run('Reprocess outdated', '/reprocess-outdated')}>Reprocess outdated</Button>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={logout}>
          <LogOut /> Log out
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">Session expires {timeAgo(session.expires_at)}. Actions queue jobs for the worker.</p>
      {msg && (
        <p role="status" className={`rounded-md border p-2 text-sm ${msg.ok ? '' : 'border-destructive text-destructive'}`}>
          {msg.text}
        </p>
      )}

      <Section title="Sources">
        {sources.isPending ? <ListSkeleton rows={3} /> : sources.isError ? <ErrorState error={sources.error} retry={() => sources.refetch()} /> : (
          <Table head={['Source', 'State', 'Last fetch', 'Last status', '']}>
            {sources.data.map((s) => (
              <tr key={s.key}>
                <td><span className="font-medium">{s.name}</span> <span className="text-muted-foreground">({s.key})</span></td>
                <td>{!s.enabled ? 'disabled in config' : s.admin_disabled ? 'paused' : 'active'}</td>
                <td>{timeAgo(s.last_fetched_at)}</td>
                <td className={s.last_error ? 'text-destructive' : undefined} title={s.last_error ?? undefined}>{s.last_status ?? '–'}</td>
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

      <Section title="Categories">
        {categories.isPending ? <ListSkeleton rows={3} /> : categories.isError ? <ErrorState error={categories.error} retry={() => categories.refetch()} /> : (
          <Table head={['Name', 'Description', 'Enabled', '']}>
            {categories.data.map((c) => (
              <CategoryRow key={c.slug} c={c} save={(slug, body) => run(`Update ${slug}`, `/categories/${slug}`, body, 'PATCH')} />
            ))}
          </Table>
        )}
      </Section>

      <Section title="Jobs">
        {jobs.isPending ? <ListSkeleton rows={3} /> : jobs.isError ? <ErrorState error={jobs.error} retry={() => jobs.refetch()} /> : (
          <Table head={['#', 'Kind', 'Status', 'Attempts', 'Created', 'Last error', '']}>
            {jobs.data.map((j) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>{j.kind}{typeof j.payload.source === 'string' && ` · ${j.payload.source}`}</td>
                <td className={j.status === 'dead_letter' ? 'text-destructive' : undefined}>{j.status}</td>
                <td className="tabular-nums">{j.attempt_count}/{j.max_attempts}</td>
                <td>{timeAgo(j.created_at)}</td>
                <td className="max-w-xs truncate" title={j.last_error ?? undefined}>{j.last_error ?? ''}</td>
                <td>{j.status === 'dead_letter' && <Button size="sm" variant="ghost" onClick={() => run(`Retry job ${j.id}`, `/jobs/${j.id}/retry`)}>Retry</Button>}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Runs">
        {runs.isPending ? <ListSkeleton rows={3} /> : runs.isError ? <ErrorState error={runs.error} retry={() => runs.refetch()} /> : (
          <Table head={['#', 'Kind', 'Started', 'Status', 'Fetched', 'New', 'Published', 'Rejected', 'Cost', 'Note']}>
            {runs.data.slice(0, 20).map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.kind}{r.source_key && ` · ${r.source_key}`} <span className="text-muted-foreground">({r.trigger})</span></td>
                <td>{timeAgo(r.started_at)}</td>
                <td className={r.status === 'failed' ? 'text-destructive' : undefined}>{r.status}</td>
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
        action={
          <div className="flex gap-1">
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
                <td className="whitespace-nowrap">{r.status}</td>
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
      <PageHeader title="Admin" />
      {body}
    </>
  )
}
