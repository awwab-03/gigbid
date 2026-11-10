import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Empty, ErrorBox, Loading } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

/** Every pending approval (proposals and client replies). Stored server-side, so a refresh never loses one. */
export default function ApprovalsPage() {
  const [d, setD] = useState<Schemas['PendingList'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/approvals')
    if (error) setErr(errorText(error)); else { setErr(null); setD(data!) }
  }, [])
  useEffect(() => { void load(); const t = setInterval(load, 6000); return () => clearInterval(t) }, [load])
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!d) return <Loading />
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Waiting for your approval</h1>
      {d.pending.length === 0 ? <Empty title="Nothing to approve">Recommended jobs get drafted automatically; drafts appear here.</Empty> : (
        <ul className="space-y-2" data-testid="pending-list">
          {d.pending.map((p) => {
            const pl = p.payload as { job_title?: string; cover_letter?: string; reply?: string; connects_cost?: number; intent?: { intent?: string } }
            const to = p.kind === 'message' ? '/messages' : `/studio/${encodeURIComponent(p.thread_id)}`
            return (
              <li key={p.thread_id} className="card flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><Badge kind="info">{p.kind}</Badge><span className="font-semibold">{pl.job_title ?? p.ref}</span>
                    {pl.intent?.intent && <Badge>{pl.intent.intent}</Badge>}</div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">{pl.cover_letter ?? pl.reply}</p>
                </div>
                <div className="flex items-center gap-3 text-xs">{pl.connects_cost != null && <span>{pl.connects_cost} Connects</span>}
                  <Link className="btn btn-primary" to={to}>Review</Link></div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
