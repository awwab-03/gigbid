import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ActionBadge, Badge, Empty, ErrorBox, Fit, Loading, RiskBadge } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

/** New jobs ranked by fit, with risk badges, recommended action, price and Connects cost. */
export default function InboxPage() {
  const [data, setData] = useState<Schemas['JobList'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'bid' | 'watch' | 'skip'>('all')
  const [q, setQ] = useState('')
  const [importId, setImportId] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/jobs', { params: { query: { action: filter === 'all' ? undefined : filter, q: q || undefined } } })
    if (error) setErr(errorText(error)); else { setErr(null); setData(data!) }
  }, [filter, q])
  useEffect(() => { void load(); const t = setInterval(load, 8000); return () => clearInterval(t) }, [load])
  const scout = async () => { const { error } = await api.POST('/jobs/scout'); setNote(error ? errorText(error) : 'Scouting queued. New jobs appear here as they are analysed.') }
  const importJob = async () => {
    if (!importId.trim()) return
    const { error } = await api.POST('/jobs/import/{job_id}', { params: { path: { job_id: importId.trim() } } })
    setNote(error ? errorText(error) : `Analysing ${importId}…`); setImportId(''); void load()
  }
  const skip = async (id: string) => { await api.POST('/jobs/{job_id}/skip', { params: { path: { job_id: id } } }); void load() }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-xl font-bold">Job inbox</h1><p className="text-sm text-muted">Ranked by fit. GigBid recommends; you decide.</p></div>
        <div className="flex flex-wrap gap-2">
          <input className="input w-36" placeholder="Job id, e.g. j-00401" value={importId} onChange={(e) => setImportId(e.target.value)} aria-label="Import job by id" data-testid="import-id" />
          <button className="btn" onClick={importJob} data-testid="import">Analyse job</button>
          <button className="btn btn-primary" onClick={scout}>Scout now</button>
        </div>
      </div>
      {note && <p className="text-sm text-brand" role="status">{note}</p>}
      {data && !data.marketplace_available && <ErrorBox message={data.marketplace_message ?? 'Marketplace unavailable'} />}
      <div className="flex flex-wrap items-center gap-2">
        {(['all', 'bid', 'watch', 'skip'] as const).map((f) => (
          <button key={f} className={`btn ${filter === f ? 'btn-primary' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>
        ))}
        <input className="input max-w-xs" placeholder="Filter titles" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter titles" />
      </div>
      {err && <ErrorBox message={err} onRetry={load} />}
      {!data && !err && <Loading />}
      {data && data.jobs.length === 0 && <Empty title="No jobs yet">Press <strong>Scout now</strong> to run your saved searches, or analyse a job by id.</Empty>}
      {data && data.jobs.length > 0 && (
        <ul className="space-y-2" data-testid="job-list">
          {data.jobs.map((j) => (
            <li key={j.job_id} className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <Link to={`/jobs/${j.job_id}`} className="font-semibold hover:text-brand">{j.title ?? j.job_id}</Link>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <ActionBadge action={j.action} /><RiskBadge risk={j.risk} scam={j.scam} />
                  {j.flags?.includes('prompt_injection') && <Badge kind="warn" title="Instructions aimed at AI were found and ignored">Injection ignored</Badge>}
                  {j.status === 'analysing' && <Badge kind="info">Analysing…</Badge>}
                  {j.status === 'awaiting_approval' && <Badge kind="info">Awaiting your approval</Badge>}
                  {j.status === 'queued_degraded' && <Badge kind="warn">Queued (marketplace down)</Badge>}
                  <span className="text-muted">{j.category} · {j.job_id}</span>
                </div>
                {j.reason && <p className="mt-1 line-clamp-1 text-xs text-muted">{j.reason}</p>}
              </div>
              <div className="flex flex-none items-center gap-4">
                <Fit value={j.fit} />
                <div className="text-right text-xs">
                  <div className="font-semibold">{j.price ? `$${j.price}${j.bid_type === 'hourly' ? '/hr' : ''}` : '–'}</div>
                  <div className="text-muted">{j.connects ?? '–'} Connects</div>
                </div>
                {j.status === 'awaiting_approval' && j.thread_id
                  ? <Link className="btn btn-primary" to={`/studio/${encodeURIComponent(j.thread_id)}`}>Review</Link>
                  : <Link className="btn" to={`/jobs/${j.job_id}`}>Open</Link>}
                {j.action !== 'skip' && <button className="btn" onClick={() => skip(j.job_id)} aria-label={`Skip ${j.title}`}>Skip</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
