// WordPress membership site (synthetic portfolio sample)
document.addEventListener('DOMContentLoaded', () => {
import Stripe from 'stripe'

export async function handler(req: Request): Promise<Response> {
  // core flow: a custom plugin for members-only content and recurring payments
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
