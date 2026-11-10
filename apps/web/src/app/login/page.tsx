import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { api, errorText } from '../../lib/client'

const PERSONAS = [
  ['ml_engineer', 'AI/ML engineer', 'LLM apps, RAG, predictive models'],
  ['fullstack_dev', 'Full-stack web developer', 'React, Next.js, Node, Django'],
  ['data_analyst', 'Data analyst', 'SQL, dashboards, dbt, Python'],
] as const

/** Sign-in and onboarding: create an account, choose a persona (GigSim account), set rates and Connects budget. */
export default function LoginPage() {
  const { user, signIn } = useAuth()
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [account, setAccount] = useState<(typeof PERSONAS)[number][0]>('ml_engineer')
  const [floor, setFloor] = useState('')
  const [budget, setBudget] = useState('80')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/inbox" replace />
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    const res = mode === 'login'
      ? await api.POST('/auth/login', { body: { email, password } })
      : await api.POST('/auth/register', { body: { email, password, name, account } })
    if (res.error || !res.data) { setBusy(false); setErr(errorText(res.error)); return }
    signIn(res.data.access_token, res.data.user)
    if (mode === 'register') {
      await api.PUT('/settings', { body: { autonomy: 'suggest', marketplace_mode: 'gigsim', weekly_connects_budget: Number(budget) || 80,
        hourly_floor: floor ? Number(floor) : null, saved_searches: [{ query: '', category: null, limit: 20 }], timezone: 'Asia/Karachi' } })
    }
    setBusy(false)
    nav('/inbox')
  }
  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-md space-y-4 p-6" aria-labelledby="title">
        <div>
          <h1 id="title" className="text-2xl font-bold text-brand">GigBid</h1>
          <p className="text-sm text-muted">Agents find and draft. You approve every proposal and message.</p>
        </div>
        <div role="tablist" className="flex gap-2">
          {(['login', 'register'] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={`btn flex-1 ${mode === m ? 'btn-primary' : ''}`} onClick={() => setMode(m)}>
              {m === 'login' ? 'Sign in' : 'Create account'}
            </button>
          ))}
        </div>
        {mode === 'register' && (
          <label className="block"><span className="label">Name</span><input className="input mt-1" value={name} onChange={(e) => setName(e.target.value)} required /></label>
        )}
        <label className="block"><span className="label">Email</span><input className="input mt-1" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="email" /></label>
        <label className="block"><span className="label">Password</span><input className="input mt-1" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="password" /></label>
        {mode === 'register' && (
          <>
            <fieldset>
              <legend className="label mb-1">Profile (GigSim marketplace account)</legend>
              <div className="space-y-2">
                {PERSONAS.map(([id, label, sub]) => (
                  <label key={id} className={`flex cursor-pointer items-start gap-2 rounded-lg border p-2 ${account === id ? 'border-brand bg-brand-soft' : 'border-line'}`}>
                    <input type="radio" name="persona" checked={account === id} onChange={() => setAccount(id)} className="mt-1" />
                    <span><span className="block text-sm font-medium">{label}</span><span className="text-xs text-muted">{sub}</span></span>
                  </label>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted">Connect a live Upwork account later in Settings (OAuth). Add your own case studies there too.</p>
            </fieldset>
            <div className="grid grid-cols-2 gap-3">
              <label><span className="label">Hourly floor (USD)</span><input className="input mt-1" type="number" min={1} value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="persona default" /></label>
              <label><span className="label">Weekly Connects</span><input className="input mt-1" type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} /></label>
            </div>
          </>
        )}
        {err && <p role="alert" className="text-sm text-bad">{err}</p>}
        <button className="btn btn-primary w-full justify-center" disabled={busy} data-testid="submit">{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
    </div>
  )
}
