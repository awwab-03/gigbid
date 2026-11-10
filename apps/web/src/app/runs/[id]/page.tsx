import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { RunTimeline } from '../../../components/RunTimeline'
import { Badge, ErrorBox, Loading, Section } from '../../../components/ui'
import { api, errorText, type Schemas } from '../../../lib/client'

/** Live node-by-node progress, trace link, per-node latency/cost, checkpoint history with replay. */
export default function RunPage() {
  const { id = '' } = useParams()
  const thread = decodeURIComponent(id)
  const [r, setR] = useState<Schemas['RunOut'] | null>(null)
  const [hist, setHist] = useState<Schemas['CheckpointOut'][]>([])
  const [err, setErr] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    const [a, b] = await Promise.all([api.GET('/runs/{thread_id}', { params: { path: { thread_id: thread } } }),
      api.GET('/runs/{thread_id}/history', { params: { path: { thread_id: thread } } })])
    if (a.error) { setErr(errorText(a.error)); return }
    setR(a.data!); setHist(b.data ?? [])
  }, [thread])
  useEffect(() => { void load() }, [load])
  const replay = async (cid: string) => {
    const { error } = await api.POST('/runs/{thread_id}/replay', { params: { path: { thread_id: thread } }, body: { checkpoint_id: cid } })
    setNote(error ? errorText(error) : 'Replay started from that checkpoint; progress streams above.')
  }
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!r) return <Loading />
  const st = r.state as { status?: string; status_reason?: string; job?: { job_id?: string } }
  return (
    <div className="space-y-4">
      <div><Link to="/runs" className="text-sm text-brand">← Runs</Link>
        <h1 className="mt-1 break-all font-mono text-base font-bold">{thread}</h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs"><Badge>{r.status}</Badge>
          <span className="text-muted">trace id {r.trace_id}</span>
          {r.trace_url ? <a className="text-brand underline" href={r.trace_url} target="_blank" rel="noreferrer">Open full trace</a> : <span className="text-muted">(trace link appears when LangSmith is configured)</span>}
          {st.job?.job_id && <Link className="text-brand underline" to={`/jobs/${st.job.job_id}`}>Job</Link>}
          {r.status === 'awaiting_approval' && <Link className="btn btn-primary" to={`/studio/${encodeURIComponent(thread)}`}>Review</Link>}
          {(r.status === 'queued_degraded' || r.status === 'dead_letter') && <button className="btn" onClick={async () => { await api.POST('/runs/{thread_id}/retry', { params: { path: { thread_id: thread } } }); setNote('Retry queued.') }}>Retry</button>}
        </div>
        {st.status_reason && <p className="mt-1 text-sm text-muted">{st.status_reason}</p>}
        {note && <p className="mt-1 text-sm text-brand" role="status">{note}</p>}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><Section title="Progress (live)"><RunTimeline threadId={thread} onFinished={() => void load()} /></Section></div>
        <div className="space-y-4">
          <Section title="Budget">
            <p className="text-sm">{r.tokens ?? 0} tokens · ${(r.cost_usd ?? 0).toFixed(4)} · {r.latency_s?.toFixed(1) ?? '–'}s</p>
            <ul className="mt-2 space-y-0.5 text-xs text-muted">{Object.entries(r.node_latency ?? {}).map(([k, v]) => <li key={k}>{k}: {v.toFixed(2)}s</li>)}</ul>
          </Section>
          <Section title="Checkpoints (replay from any node)">
            <ol className="max-h-80 space-y-1 overflow-y-auto text-xs">
              {hist.map((h) => (
                <li key={h.checkpoint_id} className="flex items-center justify-between gap-2">
                  <span>step {h.step} → {h.next.join(', ') || 'end'} <span className="text-muted">{h.status}</span></span>
                  {h.next.length > 0 && <button className="btn px-2 py-0.5 text-xs" onClick={() => replay(h.checkpoint_id)}>Replay</button>}
                </li>
              ))}
            </ol>
          </Section>
        </div>
      </div>
    </div>
  )
}
