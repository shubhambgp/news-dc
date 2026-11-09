import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Download } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Markdown } from '@/components/Markdown'
import { ErrorState, ListSkeleton, PageHeader } from '@/components/common'
import { Button } from '@/components/ui/button'
import { api, type RisingTerm } from '@/lib/api'
import { fmtDate, fmtUsd, safeUrl, timeAgo, useTitle } from '@/lib/format'

// Every chart is a single series: one hue (the theme's primary), axes and grid in muted ink.
const AXIS = { fontSize: 11, fill: 'var(--muted-foreground)' }
const TIP = {
  contentStyle: { background: 'var(--popover)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--popover-foreground)' },
  cursor: { fill: 'var(--muted)', opacity: 0.6 },
}

type Row = { label: string; value: number }

function Panel({ title, children, rows, className }: { title: string; children: ReactNode; rows?: Row[]; className?: string }) {
  return (
    <section className={`rounded-lg border bg-card p-4 ${className ?? ''}`} aria-label={title}>
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
      {rows && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground">Show as table</summary>
          <table className="mt-2 w-full">
            <tbody>
              {rows.map((r) => (
                <tr key={r.label} className="border-t">
                  <th scope="row" className="py-1 text-left font-normal">
                    {r.label}
                  </th>
                  <td className="py-1 text-right tabular-nums">{r.value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  )
}

function HBars({ rows, name = 'Items' }: { rows: Row[]; name?: string }) {
  return (
    <div style={{ height: Math.max(120, rows.length * 26 + 20) }} aria-hidden>
      <ResponsiveContainer>
        <BarChart accessibilityLayer={false} data={rows} layout="vertical" margin={{ left: 0, right: 16, top: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" tick={AXIS} stroke="var(--border)" />
          <YAxis type="category" dataKey="label" width={130} tick={AXIS} stroke="var(--border)" interval={0} />
          <Tooltip {...TIP} />
          <Bar isAnimationActive={false} dataKey="value" name={name} fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function Rising({ title, terms }: { title: string; terms: RisingTerm[] }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold text-muted-foreground uppercase">{title}</h3>
      {terms.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing rising this week.</p>
      ) : (
        <ol className="space-y-1 text-sm">
          {terms.slice(0, 6).map((t) => (
            <li key={t.term} className="flex items-baseline justify-between gap-2">
              <Link to={`/search?q=${encodeURIComponent(t.term)}`} className="truncate hover:underline">
                {t.term}
              </Link>
              <span className="shrink-0 text-xs text-emerald-700 tabular-nums dark:text-emerald-400" title={`${t.recent} items this week, ${t.baseline} in the 4 weeks before`}>
                {t.new ? 'new' : `+${t.change_pct}%`} <span className="text-muted-foreground">({t.recent})</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export default function DashboardPage() {
  useTitle('Dashboard', 'Ingestion funnel, categories, sources, rising topics and the weekly trend brief.')
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })
  const trends = useQuery({ queryKey: ['trends'], queryFn: api.trends })

  if (stats.isPending) return <ListSkeleton />
  if (stats.isError) return <ErrorState error={stats.error} retry={() => stats.refetch()} />
  const s = stats.data
  const f = s.funnel
  const funnel: Row[] = [
    { label: 'Fetched', value: f.fetched },
    { label: 'Rejected (prefilter)', value: f.rejected_prefilter },
    { label: 'Rejected (AI)', value: f.rejected_ai },
    { label: 'Duplicates', value: f.duplicate },
    { label: 'Failed', value: f.failed },
    { label: 'Waiting', value: f.new },
    { label: 'Published', value: f.processed },
  ]
  const cats = s.by_category.map((c) => ({ label: c.name, value: c.items }))
  const types = s.by_content_type.map((c) => ({ label: c.key[0].toUpperCase() + c.key.slice(1), value: c.items }))
  const sources = s.by_source.filter((x) => x.items).map((x) => ({ label: x.name, value: x.processed }))
  const brief = trends.data?.brief

  return (
    <>
      <PageHeader title="Dashboard">
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={api.exportUrl('json', { limit: 1000 })} download>
              <Download /> Export JSON
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={api.exportUrl('md', { limit: 1000 })} download>
              <Download /> Export Markdown
            </a>
          </Button>
        </div>
      </PageHeader>

      <dl className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Items collected', f.fetched.toLocaleString()],
          ['Published', f.processed.toLocaleString()],
          ['Pass rate', f.fetched ? `${Math.round((f.processed / f.fetched) * 100)}%` : '–'],
          ['AI cost (total)', fmtUsd(s.ai_cost.total_usd)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border bg-card p-3">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="text-2xl font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Items published per day (60 days)" rows={s.per_day.map((d) => ({ label: d.date, value: d.items }))} className="lg:col-span-2">
          <div className="h-48" aria-hidden>
            <ResponsiveContainer>
              <AreaChart accessibilityLayer={false} data={s.per_day} margin={{ left: -20, right: 8, top: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
                <YAxis tick={AXIS} stroke="var(--border)" allowDecimals={false} />
                <Tooltip {...TIP} cursor={{ stroke: 'var(--muted-foreground)' }} />
                <Area isAnimationActive={false} type="monotone" dataKey="items" name="Items" stroke="var(--primary)" strokeWidth={2} fill="var(--primary)" fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Ingestion funnel" rows={funnel}>
          <HBars rows={funnel} />
        </Panel>

        <Panel title="Rising topics (last 7 days vs the 4 weeks before)">
          {trends.isPending ? (
            <ListSkeleton rows={3} />
          ) : trends.isError ? (
            <ErrorState error={trends.error} retry={() => trends.refetch()} />
          ) : (
            <div className="grid gap-4 sm:grid-cols-3">
              <Rising title="Tags" terms={trends.data.tags} />
              <Rising title="Companies" terms={trends.data.companies} />
              <Rising title="Technologies" terms={trends.data.technologies} />
            </div>
          )}
        </Panel>

        <Panel title="Published items by category" rows={cats}>
          <HBars rows={cats} />
        </Panel>

        <div className="space-y-4">
          <Panel title="By content type" rows={types}>
            <HBars rows={types} />
          </Panel>
          <Panel title="Published items by source" rows={sources}>
            <HBars rows={sources} />
          </Panel>
        </div>

        <Panel title="Weekly trend brief" className="lg:col-span-2">
          {!brief ? (
            <p className="text-sm text-muted-foreground">No brief yet. One is written every Monday.</p>
          ) : (
            <>
              <p className="mb-2 text-xs text-muted-foreground">
                {fmtDate(brief.period_start)} – {fmtDate(brief.period_end)} · written by AI ({brief.model}) {timeAgo(brief.created_at)}
              </p>
              <Markdown text={brief.content_md} known={new Set(brief.sources.map((x) => x.n))} idPrefix="brief" />
              <details className="mt-3">
                <summary className="cursor-pointer text-sm text-muted-foreground">Sources ({brief.sources.length})</summary>
                <ol className="mt-2 space-y-1 text-xs">
                  {brief.sources.map((x) => (
                    <li key={x.n} id={`brief-${x.n}`} className="scroll-mt-20 target:bg-primary/10">
                      [{x.n}]{' '}
                      <a href={safeUrl(x.url)} target="_blank" rel="noopener noreferrer" className="hover:underline">
                        {x.title}
                      </a>{' '}
                      <span className="text-muted-foreground">
                        {x.publisher} · {fmtDate(x.published_at)} ·{' '}
                        <Link to={`/article/${x.id}`} className="text-primary hover:underline">
                          summary
                        </Link>
                      </span>
                    </li>
                  ))}
                </ol>
              </details>
            </>
          )}
        </Panel>

        <Panel title="AI cost estimate">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">Classifier, total</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.classifier_usd)}</dd>
            <dt className="text-muted-foreground">Classifier, today</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.classifier_today_usd)}</dd>
            <dt className="text-muted-foreground">Trend briefs</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.trend_brief_usd)}</dd>
            <dt className="font-medium">Total</dt>
            <dd className="text-right font-medium tabular-nums">{fmtUsd(s.ai_cost.total_usd)}</dd>
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">Estimated from token counts. Ask NewsDC answers are not included.</p>
        </Panel>

        <Panel title="Last pipeline runs">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-1 font-normal">Run</th>
                  <th className="font-normal">Started</th>
                  <th className="font-normal">Status</th>
                  <th className="text-right font-normal">New</th>
                  <th className="text-right font-normal">Published</th>
                  <th className="text-right font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {s.pipeline_runs.map((r) => (
                  <tr key={r.id} className="border-t" title={r.error ?? r.stop_reason ?? undefined}>
                    <td className="py-1">
                      {r.kind}
                      {r.source_key && ` · ${r.source_key}`}
                    </td>
                    <td>{timeAgo(r.started_at)}</td>
                    <td className={r.status === 'failed' ? 'text-destructive' : undefined}>{r.status}</td>
                    <td className="text-right tabular-nums">{r.new}</td>
                    <td className="text-right tabular-nums">{r.processed}</td>
                    <td className="text-right tabular-nums">{fmtUsd(r.cost_usd_estimate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link to="/admin" className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline">
            Admin <ArrowUpRight className="size-3" />
          </Link>
        </Panel>
      </div>
    </>
  )
}
