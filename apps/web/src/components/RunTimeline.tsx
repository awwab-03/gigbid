import { useEffect, useRef, useState } from 'react'
import { streamRun } from '../lib/client'

type Ev = { id: number; type: string; node?: string | null; data?: Record<string, unknown>; at?: string }
const LABEL: Record<string, string> = {
  intake: 'Scout intake', analyst: 'Job Analyst', risk_assessor: 'Risk Assessor', fit_matcher: 'Fit Matcher', decide: 'Bid decision',
  pricing: 'Pricing Strategist', writer: 'Proposal Writer', verifier: 'Claim verification', critic: 'Critic', revise: 'Revision',
  compliance: 'Compliance Guard', approval: 'Human approval', submit: 'Submit (marketplace)', load_thread: 'Read thread',
  classify: 'Intent', plan_reply: 'Calendar slots', draft_reply: 'Client Liaison draft', reply_compliance: 'Compliance', reply_approval: 'Human approval', send: 'Send',
}

/** Live node-by-node progress streamed from LangGraph over SSE; reconnects from the last event id. */
export function RunTimeline({ threadId, onFinished }: { threadId: string; onFinished?: (status: string) => void }) {
  const [events, setEvents] = useState<Ev[]>([])
  const [live, setLive] = useState(true)
  const last = useRef(0)
  const done = useRef(onFinished)
  done.current = onFinished
  useEffect(() => {
    const ctl = new AbortController()
    let stop = false
    const run = async () => {
      while (!stop) {
        try {
          setLive(true)
          await streamRun(threadId, (type, raw, id) => {
            last.current = Math.max(last.current, id)
            const d = raw as { node?: string; data?: Record<string, unknown>; at?: string }
            setEvents((e) => (e.some((x) => x.id === id) ? e : [...e, { id, type, node: d.node, data: d.data, at: d.at }]))
            if (type === 'run_finished' || type === 'approval_required') done.current?.(String(d.data?.status ?? type))
          }, ctl.signal, last.current)
        } catch { if (stop) return }
        setLive(false)
        await new Promise((r) => setTimeout(r, 3000))
      }
    }
    void run()
    return () => { stop = true; ctl.abort() }
  }, [threadId])
  return (
    <div>
      <p className="mb-2 text-xs text-muted" aria-live="polite">{live ? 'Live' : 'Reconnecting…'} · {events.length} events</p>
      <ol className="space-y-1.5" data-testid="run-timeline">
        {events.filter((e) => e.type !== 'run_started').map((e) => (
          <li key={e.id} className="flex items-start gap-2 text-sm">
            <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${e.type === 'error' ? 'bg-bad' : e.type === 'approval_required' ? 'bg-warn' : 'bg-good'}`} />
            <span className="min-w-0">
              <span className="font-medium">{e.node ? LABEL[e.node] ?? e.node : e.type.replace('_', ' ')}</span>
              {e.data?.summary ? <span className="text-muted"> — {String(e.data.summary)}</span> : null}
              {e.data?.status ? <span className="text-muted"> ({String(e.data.status)})</span> : null}
              {typeof e.data?.latency_s === 'number' && <span className="ml-1 text-xs tabular-nums text-muted">{(e.data.latency_s as number).toFixed(1)}s</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
