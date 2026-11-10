import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Empty, ErrorBox, Loading } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

export default function RunsPage() {
  const [d, setD] = useState<Schemas['RunOut'][] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    const load = async () => { const { data, error } = await api.GET('/runs'); if (error) setErr(errorText(error)); else setD(data!) }
    void load(); const t = setInterval(load, 6000); return () => clearInterval(t)
  }, [])
  if (err) return <ErrorBox message={err} />
  if (!d) return <Loading />
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Agent runs</h1>
      {d.length === 0 ? <Empty title="No runs yet" /> : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="p-3">Thread</th><th className="p-3">Status</th><th className="p-3">Latency</th><th className="p-3">Tokens</th><th className="p-3">Cost</th></tr></thead>
            <tbody>{d.map((r) => (
              <tr key={r.thread_id} className="border-t border-line">
                <td className="p-3"><Link className="font-mono text-xs text-brand" to={`/runs/${encodeURIComponent(r.thread_id)}`}>{r.thread_id}</Link></td>
                <td className="p-3"><Badge kind={r.status === 'submitted' || r.status === 'sent' ? 'good' : r.status === 'failed' || r.status === 'dead_letter' ? 'bad' : 'muted'}>{r.status}</Badge></td>
                <td className="p-3 tabular-nums">{r.latency_s?.toFixed(1) ?? '–'}s</td><td className="p-3 tabular-nums">{r.tokens ?? 0}</td><td className="p-3 tabular-nums">${(r.cost_usd ?? 0).toFixed(4)}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}
