import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { RunTimeline } from '../../../components/RunTimeline'
import { ActionBadge, Badge, ErrorBox, Fit, Loading, RiskBadge, Section } from '../../../components/ui'
import { api, errorText, type Schemas } from '../../../lib/client'

type Ev = { evidence_id: string; project_title?: string; type: string; snippet: string; score: number }

/** JobSpec, risk report, requirement-to-evidence matrix, price rationale and bid-or-skip reasoning. */
export default function JobDetailPage() {
  const { id = '' } = useParams()
  const [d, setD] = useState<Schemas['JobDetail'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/jobs/{job_id}', { params: { path: { job_id: id } } })
    if (error) setErr(errorText(error)); else { setErr(null); setD(data!) }
  }, [id])
  useEffect(() => { void load() }, [load])
  const analyze = async (force = false) => {
    await api.POST('/jobs/{job_id}/analyze', { params: { path: { job_id: id }, query: { force } } }); setTimeout(load, 800)
  }
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!d) return <Loading />
  const a = d.analysis as Record<string, Record<string, unknown> | undefined>
  const spec = a.job_spec as Record<string, string[]> | undefined
  const risk = a.risk_report as { score?: number; scam_likely?: boolean; flags?: string[]; explanation?: string; client_quality?: number; injection_spans?: string[] } | undefined
  const fit = a.fit_report as { score?: number; matrix?: { requirement: string; supported: boolean; evidence: Ev[] }[]; variant?: string; reasons?: string[] } | undefined
  const dec = a.decision as { action?: string; reasons?: string[] } | undefined
  const price = a.price as { amount?: number; bid_type?: string; rationale?: string; connects_cost?: number; connects_worth_it?: boolean } | undefined
  const job = d.job as { title: string; description: string; budget: { type: string; min: number; max: number }; client_id: string; connects_cost: number }
  const thread = d.row?.thread_id
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/inbox" className="text-sm text-brand">← Inbox</Link>
          <h1 className="mt-1 text-xl font-bold">{job.title}</h1>
          <div className="mt-1 flex flex-wrap gap-2 text-xs"><ActionBadge action={dec?.action} /><RiskBadge risk={risk?.score} scam={risk?.scam_likely} />
            <span className="text-muted">{job.budget.type} ${job.budget.min}–{job.budget.max} · {job.connects_cost} Connects · client {job.client_id}</span></div>
        </div>
        <div className="flex gap-2">
          {d.row?.status === 'awaiting_approval' && thread && <Link className="btn btn-primary" to={`/studio/${encodeURIComponent(thread)}`}>Review proposal</Link>}
          {!d.row?.thread_id ? <button className="btn btn-primary" onClick={() => analyze()}>Analyse</button> : <button className="btn" onClick={() => analyze(true)}>Re-analyse</button>}
          {thread && <Link className="btn" to={`/runs/${encodeURIComponent(thread)}`}>Agent run</Link>}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title="Bid-or-skip reasoning">
            <p className="text-sm">{dec?.action ? <strong className="capitalize">{dec.action}</strong> : 'Not analysed yet.'} {dec?.reasons?.join(' · ')}</p>
            {a.status_reason ? <p className="mt-1 text-xs text-muted">{String(a.status_reason)}</p> : null}
          </Section>
          <Section title="Requirement → evidence matrix" right={fit && <span className="flex items-center gap-2 text-xs text-muted">fit <Fit value={fit.score} /> · {fit.variant}</span>}>
            {!fit?.matrix?.length ? <p className="text-sm text-muted">No analysis yet.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead><tr className="text-xs text-muted"><th className="py-1 pr-3">Requirement</th><th className="py-1 pr-3">Proof</th><th className="py-1">Portfolio evidence</th></tr></thead>
                  <tbody>
                    {fit.matrix.map((m) => (
                      <tr key={m.requirement} className="border-t border-line align-top">
                        <td className="py-2 pr-3 font-medium">{m.requirement}</td>
                        <td className="py-2 pr-3">{m.supported ? <Badge kind="good">proven</Badge> : <Badge kind="bad">no evidence</Badge>}</td>
                        <td className="py-2">{m.evidence.slice(0, 2).map((e) => (
                          <div key={e.evidence_id} className="mb-1 text-xs"><span className="font-medium">{e.project_title ?? e.type}</span> <span className="text-muted">({e.type})</span>
                            <p className="line-clamp-2 text-muted">{e.snippet}</p></div>
                        ))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
          <Section title="Job post (untrusted)">
            <pre className="whitespace-pre-wrap font-sans text-sm text-slate-700">{job.description}</pre>
          </Section>
        </div>
        <div className="space-y-4">
          <Section title="Risk report">
            {!risk ? <p className="text-sm text-muted">Pending.</p> : (
              <div className="space-y-2 text-sm">
                <p>Score <strong>{risk.score}</strong> · client quality {risk.client_quality}</p>
                <div className="flex flex-wrap gap-1">{(risk.flags ?? []).map((f) => <Badge key={f} kind={f === 'prompt_injection' ? 'warn' : 'muted'}>{f}</Badge>)}</div>
                <p className="text-xs text-muted">{risk.explanation}</p>
                {!!risk.injection_spans?.length && <div className="rounded border border-amber-200 bg-warn-soft p-2 text-xs"><strong>Ignored instruction-like text:</strong><ul className="list-disc pl-4">{risk.injection_spans.map((s) => <li key={s}>{s}</li>)}</ul></div>}
              </div>
            )}
          </Section>
          <Section title="Price rationale">
            {!price ? <p className="text-sm text-muted">Priced only for recommended bids.</p> : (
              <div className="text-sm"><p className="text-lg font-bold">${price.amount}{price.bid_type === 'hourly' ? '/hr' : ''}</p>
                <p className="text-xs text-muted">{price.rationale}</p>
                <p className="mt-1 text-xs">{price.connects_cost} Connects · {price.connects_worth_it ? 'worth it' : 'not worth it'}</p></div>
            )}
          </Section>
          <Section title="JobSpec">
            {!spec ? <p className="text-sm text-muted">Pending.</p> : (
              <dl className="space-y-1 text-xs">{(['requirements', 'deliverables', 'hidden_needs', 'screening_questions'] as const).map((k) => (
                <div key={k}><dt className="label">{k.replace('_', ' ')}</dt><dd>{(spec[k] ?? []).join(' · ') || '–'}</dd></div>))}</dl>
            )}
          </Section>
          {thread && <Section title="Live progress"><RunTimeline threadId={thread} onFinished={() => void load()} /></Section>}
        </div>
      </div>
    </div>
  )
}
