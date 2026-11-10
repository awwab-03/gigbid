import { useCallback, useEffect, useState } from 'react'
import { Badge, ErrorBox, Loading, Section } from '../../components/ui'
import { useAuth } from '../../lib/auth'
import { api, errorText, type Schemas } from '../../lib/client'

/** Autonomy, budgets, saved searches, rates, connected accounts, portfolio upload, and the memory viewer. */
export default function SettingsPage() {
  const { user, refresh } = useAuth()
  const [s, setS] = useState<Schemas['Settings'] | null>(null)
  const [mem, setMem] = useState<Schemas['MemoryOut'] | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = useCallback(async () => {
    const [a, b] = await Promise.all([api.GET('/settings'), api.GET('/memory')])
    if (!a.data) setErr('Could not load settings'); else setS(a.data)
    if (b.data) setMem(b.data)
  }, [])
  useEffect(() => { void load() }, [load])
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!s) return <Loading />
  const save = async () => { const { error } = await api.PUT('/settings', { body: s }); setMsg(error ? errorText(error) : 'Saved.'); void refresh() }
  const forget = async (kind: string, key: string, category?: string) => {
    const { data } = await api.DELETE('/memory/{kind}/{key}', { params: { path: { kind, key }, query: { category } } }); if (data) setMem(data)
  }
  const connectUpwork = async () => {
    const { data, error } = await api.GET('/auth/upwork/start')
    if (error || !data) setMsg(`Could not start Upwork OAuth: ${errorText(error)}`); else window.location.href = String((data as { authorize_url: string }).authorize_url)
  }
  const upload = async (f: File | undefined) => {
    if (!f) return
    const fd = new FormData(); fd.append('file', f)
    const { error } = await api.POST('/portfolio/upload', { body: fd as never, bodySerializer: (b) => b as unknown as FormData, params: { query: { project_title: f.name.replace(/\.(md|txt)$/, '') } } })
    setMsg(error ? errorText(error) : `Added ${f.name}; only new chunks were embedded.`)
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Settings</h1>
      {msg && <p role="status" className="text-sm text-brand">{msg}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Autonomy and budgets">
          <div className="space-y-3 text-sm">
            <label className="block"><span className="label">Autonomy</span>
              <select className="input mt-1" value={s.autonomy} onChange={(e) => setS({ ...s, autonomy: e.target.value as 'suggest' | 'auto_skip' })}>
                <option value="suggest">Suggest only</option><option value="auto_skip">Auto-skip low-fit jobs (never auto-send)</option></select></label>
            <div className="grid grid-cols-3 gap-2">
              <label><span className="label">Weekly Connects</span><input className="input mt-1" type="number" value={s.weekly_connects_budget} onChange={(e) => setS({ ...s, weekly_connects_budget: Number(e.target.value) })} /></label>
              <label><span className="label">Hourly floor</span><input className="input mt-1" type="number" value={s.hourly_floor ?? ''} onChange={(e) => setS({ ...s, hourly_floor: e.target.value ? Number(e.target.value) : null })} /></label>
              <label><span className="label">Min fixed $</span><input className="input mt-1" type="number" value={s.min_fixed ?? ''} onChange={(e) => setS({ ...s, min_fixed: e.target.value ? Number(e.target.value) : null })} /></label>
            </div>
          </div>
        </Section>
        <Section title="Saved searches" right={<button className="btn" onClick={() => setS({ ...s, saved_searches: [...(s.saved_searches ?? []), { query: '', category: null, limit: 20 }] })}>Add</button>}>
          <ul className="space-y-2">{(s.saved_searches ?? []).map((q, i) => (
            <li key={i} className="flex gap-2">
              <input className="input" placeholder="keywords" value={q.query ?? ''} aria-label={`Search ${i + 1} keywords`} onChange={(e) => { const n = [...(s.saved_searches ?? [])]; n[i] = { ...q, query: e.target.value }; setS({ ...s, saved_searches: n }) }} />
              <button className="btn" aria-label={`Remove search ${i + 1}`} onClick={() => setS({ ...s, saved_searches: (s.saved_searches ?? []).filter((_, j) => j !== i) })}>✕</button>
            </li>))}</ul>
        </Section>
        <Section title="Connected accounts">
          <div className="space-y-2 text-sm">
            <p>GigSim account: <strong>{user?.account}</strong> <Badge kind="good">connected</Badge></p>
            <p>Upwork (official MCP, OAuth 2.1): {user?.upwork_connected ? <Badge kind="good">connected</Badge> : <button className="btn" onClick={connectUpwork}>Connect Upwork</button>}</p>
            <label className="block"><span className="label">Marketplace mode</span>
              <select className="input mt-1" value={s.marketplace_mode} onChange={(e) => setS({ ...s, marketplace_mode: e.target.value as 'gigsim' | 'upwork_live' })}>
                <option value="gigsim">GigSim (simulator)</option><option value="upwork_live">Upwork live (drafts only, you confirm on Upwork)</option></select></label>
          </div>
        </Section>
        <Section title="Portfolio">
          <label className="text-sm"><span className="label">Add a case study (.md or .txt)</span>
            <input className="mt-2 block text-sm" type="file" accept=".md,.txt" onChange={(e) => upload(e.target.files?.[0])} /></label>
        </Section>
      </div>
      <button className="btn btn-primary" onClick={save}>Save settings</button>
      <Section title="What GigBid has learned (memory)">
        {!mem ? <Loading /> : (
          <div className="grid gap-4 md:grid-cols-2" data-testid="memory">
            <div><p className="label mb-1">Style rules (from your edits)</p>
              {mem.style.length === 0 ? <p className="text-sm text-muted">Nothing yet. A rule is learned after the same edit appears in 3 different drafts.</p> :
                <ul className="space-y-1">{mem.style.map((m) => (
                  <li key={String(m.key)} className="flex items-start justify-between gap-2 text-sm"><span>{String(m.rule)} <span className="text-xs text-muted">({String(m.evidence_edits)} edits, {String(m.consistency)} consistent)</span></span>
                    <button className="btn px-2 py-0.5 text-xs" onClick={() => forget('style', String(m.key))}>Delete</button></li>))}</ul>}</div>
            <div><p className="label mb-1">Outcome insights (from marketplace results)</p>
              {mem.outcome.length === 0 ? <p className="text-sm text-muted">Nothing yet.</p> :
                <ul className="space-y-1">{mem.outcome.map((m) => (
                  <li key={String(m.key) + String(m.category)} className="flex items-start justify-between gap-2 text-sm"><span>{String(m.insight)}</span>
                    <button className="btn px-2 py-0.5 text-xs" onClick={() => forget('outcome', String(m.key), String(m.category))}>Delete</button></li>))}</ul>}</div>
            <p className="text-xs text-muted md:col-span-2">{mem.observations.edits} edit observations and {mem.observations.outcomes} outcome observations are staged; only patterns that pass the promotion rule become memory.</p>
          </div>
        )}
      </Section>
    </div>
  )
}
