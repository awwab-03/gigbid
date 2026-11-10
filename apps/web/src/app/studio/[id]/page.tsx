import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApprovalPanel } from '../../../components/ApprovalPanel'
import { EvidenceHover, type Claim } from '../../../components/EvidenceHover'
import { Badge, ErrorBox, Loading, RiskBadge, Section } from '../../../components/ui'
import { api, errorText, type Schemas } from '../../../lib/client'

/** Proposal studio: claims with evidence on hover, Critic and Compliance comments inline, regenerate one paragraph,
 *  approve / edit / reject, and the dry-run preview of what will be sent and what it costs. */
export default function StudioPage() {
  const { id = '' } = useParams()
  const thread = decodeURIComponent(id)
  const nav = useNavigate()
  const [p, setP] = useState<Schemas['Pending'] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [amount, setAmount] = useState<number | null>(null)
  const [tab, setTab] = useState<'evidence' | 'edit'>('evidence')
  const [regen, setRegen] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const load = useCallback(async () => {
    const { data, error } = await api.GET('/approvals/{thread_id}', { params: { path: { thread_id: thread } } })
    if (error) { setErr(errorText(error)); return }
    setP(data!); setText(String(data!.payload.cover_letter ?? '')); setAmount(Number((data!.payload.price as { amount?: number })?.amount ?? 0) || null)
  }, [thread])
  useEffect(() => { void load() }, [load])
  const paragraphs = useMemo(() => text.split(/\n\s*\n/).filter((x) => x.trim()), [text])
  if (done) return (
    <div className="card space-y-3 p-6" role="status" data-testid="decision-done">
      <p className="text-lg font-semibold">{done === 'reject' ? 'Rejected. The reason was saved.' : done === 'edit' ? 'Edits sent for a compliance re-check; you will approve the final text next.' : 'Approved. Submitting through the marketplace port (exactly once).'}</p>
      <div className="flex gap-2"><Link className="btn" to={`/runs/${encodeURIComponent(thread)}`}>Watch the run</Link><button className="btn" onClick={() => nav('/inbox')}>Back to inbox</button></div>
    </div>
  )
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!p) return <Loading />
  const pl = p.payload as Record<string, unknown>
  const claims = (pl.claims as Claim[] | undefined) ?? []
  const critiques = (pl.critiques as { score: number; passed: boolean; issues: string[] }[] | undefined) ?? []
  const comp = (pl.compliance as { status?: string; violations?: { rule: string; detail: string; severity: string }[] } | undefined) ?? {}
  const risk = pl.risk_report as { score?: number; scam_likely?: boolean } | undefined
  const answers = (pl.screening_answers as { question: string; answer: string }[] | undefined) ?? []
  const doRegen = async (i: number) => {
    setRegen(`Regenerating paragraph ${i + 1}…`)
    const { data, error } = await api.POST('/approvals/{thread_id}/regenerate', { params: { path: { thread_id: thread } }, body: { paragraph_index: i } })
    if (error || !data) { setRegen(errorText(error)); return }
    const next = [...paragraphs]; next[i] = data.text; setText(next.join('\n\n')); setTab('edit')
    setRegen(`Paragraph ${i + 1} rewritten from evidence (${data.unsupported_removed} unsupported claim(s) removed). Review, then approve with edits.`)
  }
  return (
    <div className="space-y-4">
      <div><Link to="/inbox" className="text-sm text-brand">← Inbox</Link>
        <h1 className="mt-1 text-xl font-bold">Proposal studio</h1>
        <p className="text-sm text-muted">{String(pl.job_title ?? '')} · <RiskBadge risk={risk?.score} scam={risk?.scam_likely} /></p></div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title="Cover letter" right={
            <div role="tablist" className="flex gap-1">
              {(['evidence', 'edit'] as const).map((t) => <button key={t} role="tab" aria-selected={tab === t} className={`btn ${tab === t ? 'btn-primary' : ''}`} onClick={() => setTab(t)}>{t === 'evidence' ? 'Claims & evidence' : 'Edit'}</button>)}
            </div>}>
            {tab === 'evidence' ? (
              <div className="text-sm leading-7" data-testid="claims-view">
                {claims.length ? claims.filter((c) => c.label !== 'unsupported').map((c, i) => <EvidenceHover key={i} claim={c} />) : <p className="whitespace-pre-wrap">{text}</p>}
                {claims.some((c) => c.label === 'unsupported') && (
                  <p className="mt-3 rounded border border-red-200 bg-bad-soft p-2 text-xs text-bad">Removed before review (no portfolio evidence): {claims.filter((c) => c.label === 'unsupported').map((c) => `“${c.claim}”`).join(' ')}</p>
                )}
                <p className="mt-2 text-xs text-muted">Hover or tab to a claim to see the evidence behind it. Green = supported, amber = partly supported (softened).</p>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="label" htmlFor="draft">Edit the text that will be sent</label>
                <textarea id="draft" className="input min-h-64 font-sans leading-6" value={text} onChange={(e) => setText(e.target.value)} data-testid="draft-editor" />
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {paragraphs.map((_, i) => <button key={i} className="btn" onClick={() => doRegen(i)}>Regenerate ¶{i + 1}</button>)}
                  <label className="ml-auto flex items-center gap-1">Bid $<input className="input w-24" type="number" value={amount ?? ''} onChange={(e) => setAmount(Number(e.target.value) || null)} aria-label="Bid amount" /></label>
                </div>
                {regen && <p className="text-xs text-brand" role="status">{regen}</p>}
              </div>
            )}
          </Section>
          {answers.length > 0 && <Section title="Screening answers">{answers.map((a) => <div key={a.question} className="mb-2 text-sm"><p className="font-medium">{a.question}</p><p className="text-slate-700">{a.answer || <em className="text-muted">left blank: no evidence</em>}</p></div>)}</Section>}
        </div>
        <div className="space-y-4">
          <Section title="Approve"><ApprovalPanel threadId={thread} text={String(pl.cover_letter ?? '')} edited={text} amount={(pl.price as { amount?: number })?.amount}
            editedAmount={amount} preview={pl.dry_run as Record<string, unknown>} connectsCost={pl.connects_cost as number | undefined} onDone={setDone} /></Section>
          <Section title="Critic">
            {critiques.map((c, i) => <div key={i} className="mb-2 text-xs"><Badge kind={c.passed ? 'good' : 'warn'}>round {i + 1}: {c.score}/10 {c.passed ? 'pass' : 'revise'}</Badge>
              <ul className="mt-1 list-disc pl-4 text-muted">{c.issues.map((x) => <li key={x}>{x}</li>)}</ul></div>)}
          </Section>
          <Section title="Compliance Guard">
            <Badge kind={comp.status === 'pass' ? 'good' : comp.status === 'block' ? 'bad' : 'warn'}>{comp.status ?? '–'}</Badge>
            <ul className="mt-2 space-y-1 text-xs text-muted">{(comp.violations ?? []).map((v, i) => <li key={i}><strong>{v.rule}</strong>: {v.detail}</li>)}</ul>
          </Section>
          <Section title="Price"><p className="text-xs text-muted">{String((pl.price as { rationale?: string })?.rationale ?? '')}</p></Section>
        </div>
      </div>
    </div>
  )
}
