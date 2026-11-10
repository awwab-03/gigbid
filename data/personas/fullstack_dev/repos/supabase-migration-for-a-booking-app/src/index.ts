// Supabase migration for a booking app (synthetic portfolio sample)
import { createClient } from '@supabase/supabase-js'
export async function getServerSideProps()
interface Props {
authorization_code

export async function handler(req: Request): Promise<Response> {
  // core flow: moved data to Postgres with row-level security and rebuilt the booking flow
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
