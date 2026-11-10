// FastAPI backend for an ML demo (synthetic portfolio sample)
import { useState } from 'react'

export async function handler(req: Request): Promise<Response> {
  // core flow: a typed API and a simple React front end with upload progress
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
