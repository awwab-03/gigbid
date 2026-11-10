import type { ReactNode } from 'react'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 p-6 text-sm text-muted">
      <span className="h-3 w-3 animate-pulse rounded-full bg-brand" /> {label}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="card flex items-center justify-between gap-4 border-red-200 bg-bad-soft p-4 text-sm text-bad">
      <span>{message}</span>
      {onRetry && <button className="btn" onClick={onRetry}>Try again</button>}
    </div>
  )
}

const tone = {
  good: 'bg-good-soft text-good', warn: 'bg-warn-soft text-warn', bad: 'bg-bad-soft text-bad',
  info: 'bg-brand-soft text-brand', muted: 'bg-slate-100 text-slate-600',
} as const

export function Badge({ children, kind = 'muted', title }: { children: ReactNode; kind?: keyof typeof tone; title?: string }) {
  return <span title={title} className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone[kind]}`}>{children}</span>
}

export function RiskBadge({ risk, scam }: { risk?: number | null; scam?: boolean }) {
  if (scam) return <Badge kind="bad" title="Likely scam">Scam risk</Badge>
  if (risk == null) return <Badge>Not assessed</Badge>
  if (risk >= 0.6) return <Badge kind="bad">High risk {risk.toFixed(2)}</Badge>
  if (risk >= 0.3) return <Badge kind="warn">Medium risk {risk.toFixed(2)}</Badge>
  return <Badge kind="good">Low risk {risk.toFixed(2)}</Badge>
}

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return <Badge>Pending</Badge>
  return <Badge kind={action === 'bid' ? 'good' : action === 'watch' ? 'warn' : 'muted'}>{action === 'bid' ? 'Recommend bid' : action}</Badge>
}

export function Fit({ value }: { value?: number | null }) {
  const v = value ?? 0
  return (
    <div className="flex items-center gap-2" aria-label={`fit ${Math.round(v * 100)} percent`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full ${v >= 0.6 ? 'bg-good' : v >= 0.45 ? 'bg-warn' : 'bg-slate-400'}`} style={{ width: `${Math.round(v * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted">{value == null ? '–' : `${Math.round(v * 100)}%`}</span>
    </div>
  )
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">{title}</h2>{right}</div>
      {children}
    </section>
  )
}
