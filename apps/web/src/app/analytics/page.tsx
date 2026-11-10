import { useEffect, useState } from 'react'
import { ErrorBox, Loading, Section } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="card p-4"><p className="label">{label}</p><p className="mt-1 text-2xl font-bold tabular-nums">{value}</p></div>
}

/** Reply and hire rate by category, Connects spent vs outcomes, cost and latency, top rejection reasons. */
export default function AnalyticsPage() {
  const [d, setD] = useState<Schemas['Analytics'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { void api.GET('/analytics').then(({ data, error }) => (error ? setErr(errorText(error)) : setD(data!))) }, [])
  if (err) return <ErrorBox message={err} />
  if (!d) return <Loading />
  const money = (x?: number | null) => (x == null ? '–' : `$${x.toFixed(4)}`)
  const sec = (x?: number | null) => (x == null ? '–' : `${x.toFixed(1)}s`)
  const max = Math.max(1, ...d.by_category.map((c) => c.submitted as number))
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Analytics</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Connects spent" value={String(d.connects_spent)} />
        <Stat label="Cost / proposal" value={money(d.cost_per_proposal_usd)} />
        <Stat label="p95 latency / proposal" value={sec(d.p95_latency_proposal_s)} />
        <Stat label="Cost / job analysed" value={money(d.cost_per_job_usd)} />
      </div>
      <Section title="Reply and hire rate by category">
        {d.by_category.length === 0 ? <p className="text-sm text-muted">No submitted proposals yet.</p> : (
          <ul className="space-y-3">{d.by_category.map((c) => (
            <li key={String(c.category)} className="text-sm">
              <div className="flex justify-between"><span className="font-medium">{String(c.category)}</span>
                <span className="tabular-nums text-muted">{String(c.submitted)} sent · reply {Math.round(Number(c.reply_rate) * 100)}% · hire {Math.round(Number(c.hire_rate) * 100)}%</span></div>
              <div className="mt-1 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-brand" style={{ width: `${(Number(c.submitted) / max) * 100}%` }}>
                <div className="h-2 rounded bg-good" style={{ width: `${Number(c.reply_rate) * 100}%` }} /></div></div>
            </li>))}</ul>
        )}
      </Section>
      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Outcomes"><ul className="text-sm">{Object.entries(d.outcomes).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="tabular-nums">{v}</span></li>)}</ul></Section>
        <Section title="Top rejection reasons">{d.top_rejection_reasons.length === 0 ? <p className="text-sm text-muted">None yet.</p> :
          <ul className="text-sm">{d.top_rejection_reasons.map((r) => <li key={String(r.reason)} className="flex justify-between"><span>{String(r.reason)}</span><span>{String(r.count)}</span></li>)}</ul>}</Section>
      </div>
      <p className="text-xs text-muted">{d.runs} agent runs · p95 latency per job analysed {sec(d.p95_latency_job_s)}</p>
    </div>
  )
}
