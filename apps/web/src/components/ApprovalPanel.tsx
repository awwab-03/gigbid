import { useState } from 'react'
import { api, errorText } from '../lib/client'

type Props = {
  threadId: string
  text: string
  edited: string
  amount?: number | null
  editedAmount?: number | null
  preview: Record<string, unknown> | undefined
  connectsCost?: number | null
  onDone: (action: string) => void
}

/** Approve / edit / reject. Edits are diffed server-side for style memory and re-checked by Compliance. */
export function ApprovalPanel({ threadId, text, edited, amount, editedAmount, preview, connectsCost, onDone }: Props) {
  const [reason, setReason] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const changed = edited.trim() !== text.trim() || (editedAmount != null && editedAmount !== amount)
  const send = async (action: 'approve' | 'edit' | 'reject') => {
    setBusy(true); setErr(null)
    const body = action === 'edit' ? { action, edited_text: edited, edited_amount: editedAmount ?? null }
      : action === 'reject' ? { action, reason } : { action }
    const { error } = await api.POST('/approvals/{thread_id}', { params: { path: { thread_id: threadId } }, body })
    setBusy(false)
    if (error) setErr(errorText(error)); else onDone(action)
  }
  const p = (preview ?? {}) as { preview?: Record<string, unknown>; marketplace?: string }
  return (
    <div className="space-y-3" data-testid="approval-panel">
      <div className="rounded-lg border border-line bg-slate-50 p-3 text-xs">
        <p className="label mb-1">Dry run: exactly what will be sent</p>
        <p>Marketplace: <strong>{p.marketplace ?? 'gigsim'}</strong> · Bid: <strong>{String(p.preview?.bid_amount ?? amount ?? '–')}</strong> ({String(p.preview?.bid_type ?? '')})
          {connectsCost != null && <> · Connects on submit: <strong data-testid="connects-cost">{connectsCost}</strong></>}</p>
        <p className="mt-1 text-muted">Nothing is sent until you approve. In live mode the draft is created on Upwork and you confirm it there.</p>
      </div>
      {err && <p role="alert" className="text-sm text-bad">{err}</p>}
      {!rejecting ? (
        <div className="flex flex-wrap gap-2">
          {changed
            ? <button className="btn btn-primary" disabled={busy} onClick={() => send('edit')} data-testid="approve-edit">Approve with my edits</button>
            : <button className="btn btn-primary" disabled={busy} onClick={() => send('approve')} data-testid="approve">Approve and send</button>}
          <button className="btn btn-danger" disabled={busy} onClick={() => setRejecting(true)} data-testid="reject">Reject…</button>
        </div>
      ) : (
        <div className="space-y-2">
          <label className="label" htmlFor="reason">Why reject? (helps GigBid learn)</label>
          <input id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. client budget too low" data-testid="reject-reason" />
          <div className="flex gap-2">
            <button className="btn btn-danger" disabled={busy || !reason.trim()} onClick={() => send('reject')} data-testid="confirm-reject">Reject</button>
            <button className="btn" onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
