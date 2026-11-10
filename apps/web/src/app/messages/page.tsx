import { useCallback, useEffect, useState } from 'react'
import { ApprovalPanel } from '../../components/ApprovalPanel'
import { Badge, Empty, ErrorBox, Loading } from '../../components/ui'
import { api, errorText, type Schemas } from '../../lib/client'

function Reply({ p, onDone }: { p: Schemas['Pending']; onDone: () => void }) {
  const pl = p.payload as { reply?: string; intent?: { intent?: string; injection_detected?: boolean }; slots?: { label: string }[]; dry_run?: Record<string, unknown> }
  const [text, setText] = useState(pl.reply ?? '')
  return (
    <div className="mt-3 space-y-2 rounded-lg border border-brand/30 bg-brand-soft/40 p-3" data-testid="suggested-reply">
      <div className="flex flex-wrap gap-2 text-xs"><Badge kind="info">suggested reply</Badge><Badge>{pl.intent?.intent}</Badge>
        {pl.intent?.injection_detected && <Badge kind="warn">instruction in client message ignored</Badge>}
        {pl.slots?.map((s) => <Badge key={s.label} kind="good">{s.label}</Badge>)}</div>
      <textarea className="input min-h-28" value={text} onChange={(e) => setText(e.target.value)} aria-label="Reply text" />
      <ApprovalPanel threadId={p.thread_id} text={pl.reply ?? ''} edited={text} preview={pl.dry_run} connectsCost={0} onDone={onDone} />
    </div>
  )
}

/** Client threads with suggested replies and interview slots; nothing is sent before approval. */
export default function MessagesPage() {
  const [d, setD] = useState<Schemas['ThreadsOut'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/messages')
    if (error) setErr(errorText(error)); else { setErr(null); setD(data!) }
  }, [])
  useEffect(() => { void load(); const t = setInterval(load, 8000); return () => clearInterval(t) }, [load])
  const draft = async (tid: string) => {
    const { error } = await api.POST('/messages/{thread_id}/draft', { params: { path: { thread_id: tid } } })
    setNote(error ? errorText(error) : 'Drafting a reply…')
  }
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!d) return <Loading />
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Messages</h1>
      {!d.marketplace_available && <ErrorBox message="Marketplace unavailable; threads will refresh when it is back." />}
      {note && <p className="text-sm text-brand" role="status">{note}</p>}
      {d.threads.length === 0 ? <Empty title="No client conversations yet">When a client replies to a proposal, the thread appears here with a suggested reply.</Empty> : (
        <ul className="space-y-3">
          {d.threads.map((t) => (
            <li key={t.thread_id} className="card p-4">
              <div className="flex items-center justify-between gap-2"><p className="font-semibold">{t.job_id}</p><Badge>{t.stage}</Badge></div>
              <ol className="mt-2 space-y-1.5">
                {(t.messages ?? []).map((m) => (
                  <li key={String(m.message_id)} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${m.sender === 'client' ? 'bg-slate-100' : 'ml-auto bg-brand-soft'}`}>
                    <span className="block text-[10px] uppercase text-muted">{String(m.sender)}</span>{String(m.body)}
                  </li>
                ))}
              </ol>
              {t.pending_reply ? <Reply p={t.pending_reply} onDone={() => { setNote('Reply decision recorded.'); void load() }} />
                : <button className="btn mt-3" onClick={() => draft(t.thread_id)}>Draft reply</button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
