import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Download, Filter, Inbox, LayoutDashboard, Newspaper, Sparkles, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Markdown } from '@/components/Markdown'
import { ErrorState, PageHeader, Skeleton, StatTile, StatusBadge } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { api, type RisingTerm } from '@/lib/api'
import { fmtDate, fmtUsd, safeUrl, timeAgo, useTitle } from '@/lib/format'

// Every chart is a single series: one hue (primary), so the title names it and no legend is needed;
// axes and grid in muted ink. Each chart also has a table view ("Show as table").
const AXIS = { fontSize: 11, fill: 'var(--muted-foreground)' }
const TIP = {
  contentStyle: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--foreground)', boxShadow: 'var(--elev-3)' },
  labelStyle: { color: 'var(--foreground)', fontWeight: 600 },
  itemStyle: { color: 'var(--foreground)' },
  cursor: { fill: 'var(--elevated)', opacity: 0.6 },
}
const short = (s: string, n = 20) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

type Row = { label: string; value: number }

function Panel({ title, description, children, rows, className }: { title: string; description?: string; children: ReactNode; rows?: Row[]; className?: string }) {
  return (
    <section className={cn('min-w-0 rounded-2xl border bg-surface p-4 shadow-card sm:p-5', className)} aria-label={title}>
      <h2 className="font-semibold">{title}</h2>
      {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      <div className="mt-4">{children}</div>
      {rows && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer py-1 text-muted-foreground hover:text-foreground">Show as table</summary>
          <table className="mt-2 w-full">
            <tbody>
              {rows.map((r) => (
                <tr key={r.label} className="border-t">
                  <th scope="row" className="py-1.5 text-left font-normal">
                    {r.label}
                  </th>
                  <td className="py-1.5 text-right tabular-nums">{r.value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  )
}

function HBars({ rows, name = 'Items', values }: { rows: Row[]; name?: string; values?: boolean }) {
  return (
    <div style={{ height: Math.max(120, rows.length * 30 + 24) }} aria-hidden>
      <ResponsiveContainer>
        <BarChart accessibilityLayer={false} data={rows} layout="vertical" margin={{ left: 0, right: values ? 48 : 16, top: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" tick={AXIS} stroke="var(--border)" tickLine={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={140}
            stroke="var(--border)"
            tickLine={false}
            interval={0}
            // One line per label (Recharts wraps long ticks); the tooltip shows the full name.
            tick={({ x, y, payload }: { x?: number | string; y?: number | string; payload?: { value?: string } }) => (
              <text x={x} y={y} dy={4} textAnchor="end" fontSize={11} fill="var(--muted-foreground)">
                {short(String(payload?.value ?? ""))}
              </text>
            )}
          />
          <Tooltip {...TIP} />
          <Bar isAnimationActive={false} dataKey="value" name={name} fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={16}>
            {values && <LabelList dataKey="value" position="right" style={{ fontSize: 11, fill: 'var(--foreground)' }} formatter={(v: unknown) => Number(v).toLocaleString()} />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function Rising({ title, terms }: { title: string; terms: RisingTerm[] }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-2 text-2xs font-semibold tracking-wider text-muted-foreground uppercase">{title}</h3>
      {terms.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing rising this week.</p>
      ) : (
        <ol className="space-y-1.5 text-sm">
          {terms.slice(0, 6).map((t) => (
            <li key={t.term} className="flex items-baseline justify-between gap-2">
              <Link to={`/search?q=${encodeURIComponent(t.term)}`} className="block min-w-0 truncate leading-6 hover:underline">
                {t.term}
              </Link>
              <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-success-ink tabular-nums" title={`${t.recent} items this week, ${t.baseline} in the 4 weeks before`}>
                <TrendingUp className="size-3" aria-hidden />
                {t.new ? 'new' : `+${t.change_pct}%`} <span className="font-normal text-muted-foreground">({t.recent})</span>
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

  if (stats.isPending)
    return (
      <div role="status" aria-label="Loading" className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 rounded-2xl" />
      </div>
    )
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

  const last7 = s.per_day.slice(-7).reduce((n, d) => n + d.items, 0)

  return (
    <>
      <PageHeader title="Dashboard" icon={LayoutDashboard} description="How NewsDC collects, filters and publishes data center news, from live counts.">
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

      <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatTile icon={Inbox} label="Items collected" value={f.fetched.toLocaleString()} sub={`${f.new.toLocaleString()} waiting for the pipeline`} tone="data" />
        <StatTile icon={Newspaper} label="Published" value={f.processed.toLocaleString()} sub={`${last7.toLocaleString()} in the last 7 days`} />
        <StatTile icon={Filter} label="Pass rate" value={f.fetched ? `${Math.round((f.processed / f.fetched) * 100)}%` : '–'} sub={`${(f.rejected_prefilter + f.rejected_ai).toLocaleString()} filtered out`} tone="success" />
        <StatTile icon={Sparkles} label="AI cost (total)" value={fmtUsd(s.ai_cost.total_usd)} sub={`${fmtUsd(s.ai_cost.classifier_today_usd)} today`} tone="ai" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2 3xl:grid-cols-3">
        <Panel title="Items published per day" description="Last 60 days, by publication date" rows={s.per_day.map((d) => ({ label: d.date, value: d.items }))} className="lg:col-span-2 3xl:col-span-3">
          <div className="h-56 3xl:h-64" aria-hidden>
            <ResponsiveContainer>
              <AreaChart accessibilityLayer={false} data={s.per_day} margin={{ left: -20, right: 8, top: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="perDayFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="date" tick={AXIS} stroke="var(--border)" tickLine={false} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
                <YAxis tick={AXIS} stroke="var(--border)" tickLine={false} allowDecimals={false} />
                <Tooltip {...TIP} cursor={{ stroke: 'var(--muted-foreground)' }} />
                <Area isAnimationActive={false} type="monotone" dataKey="items" name="Items" stroke="var(--primary)" strokeWidth={2} fill="url(#perDayFill)" activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Ingestion funnel" description="Every item fetched, and where it ended up" rows={funnel}>
          <HBars rows={funnel} values />
        </Panel>

        <Panel title="Rising topics" description="Last 7 days vs the 4 weeks before">
          {trends.isPending ? (
            <Skeleton className="h-40" />
          ) : trends.isError ? (
            <ErrorState error={trends.error} retry={() => trends.refetch()} />
          ) : (
            <div className="grid gap-5 sm:grid-cols-3">
              <Rising title="Tags" terms={trends.data.tags} />
              <Rising title="Companies" terms={trends.data.companies} />
              <Rising title="Technologies" terms={trends.data.technologies} />
            </div>
          )}
        </Panel>

        <Panel title="Published items by category" description="By primary category, so each item counts once" rows={cats}>
          <HBars rows={cats} />
        </Panel>

        <Panel title="By content type" rows={types}>
          <HBars rows={types} values />
        </Panel>

        <Panel title="Published items by source" rows={sources}>
          <HBars rows={sources} />
        </Panel>

        <section aria-labelledby="brief-title" className="ai-block min-w-0 rounded-2xl border border-ai/25 p-4 sm:p-5 lg:col-span-2 3xl:col-span-2">
          <h2 id="brief-title" className="flex flex-wrap items-center gap-2 font-semibold">
            <Sparkles className="size-4 text-ai" aria-hidden /> Weekly trend brief <Badge variant="ai">AI-generated</Badge>
          </h2>
          <div className="mt-3">
            {!brief ? (
              <p className="text-sm text-muted-foreground">No brief yet. One is written every Monday.</p>
            ) : (
              <>
                <p className="mb-2 text-xs text-muted-foreground">
                  {fmtDate(brief.period_start)} – {fmtDate(brief.period_end)} · written by AI ({brief.model}) {timeAgo(brief.created_at)}
                </p>
                <div className="max-w-[72ch]">
                  <Markdown text={brief.content_md} known={new Set(brief.sources.map((x) => x.n))} idPrefix="brief" />
                </div>
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm text-muted-foreground">Sources ({brief.sources.length})</summary>
                  <ol className="mt-2 space-y-1 text-xs">
                    {brief.sources.map((x) => (
                      <li key={x.n} id={`brief-${x.n}`} className="scroll-mt-20 rounded target:bg-primary/10">
                        [{x.n}]{' '}
                        <a href={safeUrl(x.url)} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {x.title}
                        </a>{' '}
                        <span className="text-muted-foreground">
                          {x.publisher} · {fmtDate(x.published_at)} ·{' '}
                          <Link to={`/article/${x.id}`} className="text-primary-ink hover:underline">
                            summary
                          </Link>
                        </span>
                      </li>
                    ))}
                  </ol>
                </details>
              </>
            )}
          </div>
        </section>

        <Panel title="AI cost estimate" description="Estimated from token counts. Ask NewsDC answers are not included.">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Classifier, total</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.classifier_usd)}</dd>
            <dt className="text-muted-foreground">Classifier, today</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.classifier_today_usd)}</dd>
            <dt className="text-muted-foreground">Trend briefs</dt>
            <dd className="text-right tabular-nums">{fmtUsd(s.ai_cost.trend_brief_usd)}</dd>
            <dt className="border-t pt-2 font-medium">Total</dt>
            <dd className="border-t pt-2 text-right font-semibold tabular-nums">{fmtUsd(s.ai_cost.total_usd)}</dd>
          </dl>
        </Panel>

        <Panel title="Last pipeline runs" className="lg:col-span-2 3xl:col-span-3">
          <div className="-mx-4 overflow-x-auto px-4 sm:-mx-5 sm:px-5">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-2 font-medium">Run</th>
                  <th className="font-medium">Started</th>
                  <th className="font-medium">Status</th>
                  <th className="text-right font-medium">New</th>
                  <th className="text-right font-medium">Published</th>
                  <th className="text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {s.pipeline_runs.map((r) => (
                  <tr key={r.id} className="border-t hover:bg-elevated/50" title={r.error ?? r.stop_reason ?? undefined}>
                    <td className="py-2">
                      {r.kind}
                      {r.source_key && <span className="text-muted-foreground"> · {r.source_key}</span>}
                    </td>
                    <td className="text-muted-foreground">{timeAgo(r.started_at)}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="text-right tabular-nums">{r.new}</td>
                    <td className="text-right tabular-nums">{r.processed}</td>
                    <td className="text-right tabular-nums">{fmtUsd(r.cost_usd_estimate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link to="/admin" className="mt-3 inline-flex min-h-6 items-center gap-1 text-xs font-medium text-primary-ink hover:underline">
            Admin <ArrowUpRight className="size-3" />
          </Link>
        </Panel>
      </div>
    </>
  )
}
