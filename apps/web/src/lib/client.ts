// Thin wrapper around the client generated from FastAPI's OpenAPI schema (src/lib/api/schema.d.ts).
import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './api/schema'

export type Schemas = components['schemas']
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
const TOKEN_KEY = 'gigbid.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
}

const auth: Middleware = {
  onRequest({ request }) {
    const t = getToken()
    if (t) request.headers.set('Authorization', `Bearer ${t}`)
    return request
  },
}

export const api = createClient<paths>({ baseUrl: API_URL })
api.use(auth)

export function errorText(e: unknown): string {
  if (!e) return 'Something went wrong'
  if (typeof e === 'string') return e
  const d = (e as { detail?: unknown }).detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg).join('; ')
  return 'Request failed'
}

/** Server-Sent Events over fetch (EventSource cannot send the Authorization header). */
export async function streamRun(threadId: string, onEvent: (type: string, data: unknown, id: number) => void,
                                signal: AbortSignal, after = 0) {
  const res = await fetch(`${API_URL}/runs/${encodeURIComponent(threadId)}/stream?after=${after}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ''}` }, signal,
  })
  if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`)
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(buf[i] === '\r' ? i + 4 : i + 2)
      let type = 'message', data = '', id = 0
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) type = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
        else if (line.startsWith('id:')) id = Number(line.slice(3).trim())
      }
      if (data && type !== 'ping') { try { onEvent(type, JSON.parse(data), id) } catch { /* ignore malformed */ } }
    }
  }
}
