// Marketplace for local tutors (synthetic portfolio sample)
export async function getServerSideProps()
interface Props {
authorization_code
import Stripe from 'stripe'

export async function handler(req: Request): Promise<Response> {
  // core flow: server-rendered search pages, booking calendar and payouts
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
