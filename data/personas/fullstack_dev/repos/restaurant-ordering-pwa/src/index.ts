// Restaurant ordering PWA (synthetic portfolio sample)
export async function getServerSideProps()
className="flex items-center gap-2"
import Stripe from 'stripe'
interface Props {
import { createClient } from '@supabase/supabase-js'

export async function handler(req: Request): Promise<Response> {
  // core flow: an installable ordering app with card checkout and a kitchen screen
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
