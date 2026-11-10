import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorBox, Loading } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

/** Kanban: drafted, submitted, viewed, replied, interview, hired, lost; cards move on marketplace events. */
export default function PipelinePage() {
  const [d, setD] = useState<Schemas['PipelineOut'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/pipeline')
    if (error) setErr(errorText(error)); else { setErr(null); setD(data!) }
  }, [])
  useEffect(() => { void load(); const t = setInterval(load, 8000); return () => clearInterval(t) }, [load])
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!d) return <Loading />
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Pipeline</h1>
      <div className="flex gap-3 overflow-x-auto pb-2" data-testid="kanban">
        {d.stages.map((s) => {
          const cards = d.cards.filter((c) => c.stage === s)
          return (
            <section key={s} aria-label={s} className="w-60 flex-none rounded-xl bg-slate-100 p-2">
              <h2 className="mb-2 flex justify-between px-1 text-xs font-semibold uppercase text-muted"><span>{s}</span><span>{cards.length}</span></h2>
              <ul className="space-y-2">
                {cards.map((c) => (
                  <li key={c.job_id} className="card p-3 text-sm">
                    <Link to={`/jobs/${c.job_id}`} className="font-medium hover:text-brand">{c.title ?? c.job_id}</Link>
                    <p className="mt-1 text-xs text-muted">{c.price ? `$${c.price}` : ''} {c.connects != null ? `· ${c.connects} Connects` : ''}</p>
                  </li>
                ))}
                {!cards.length && <li className="px-1 text-xs text-muted">—</li>}
              </ul>
            </section>
          )
        })}
      </div>
    </div>
  )
}
