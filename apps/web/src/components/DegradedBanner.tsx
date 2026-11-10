import { useEffect, useState } from 'react'
import { api } from '../lib/client'

/** Polls /health; when the marketplace (or its MCP server) is down the user sees why and that work is queued. */
export function DegradedBanner() {
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    const check = async () => {
      try {
        const { data, error } = await api.GET('/health')
        if (!alive) return
        if (error || !data) setMsg('GigBid API unreachable. Retrying…')
        else if (data.status !== 'ok') {
          const m = data.marketplace as { error?: string; status?: string }
          setMsg(`Marketplace unavailable${m?.error ? ` (${m.error})` : m?.status ? ` (${m.status})` : ''}. New work is queued and will resume automatically.`)
        } else setMsg(null)
      } catch { if (alive) setMsg('GigBid API unreachable. Retrying…') }
    }
    void check()
    const t = setInterval(check, 10000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  if (!msg) return null
  return (
    <div role="alert" data-testid="degraded-banner" className="border-b border-amber-200 bg-warn-soft px-4 py-2 text-sm text-warn">
      <strong>Degraded mode:</strong> {msg}
    </div>
  )
}
