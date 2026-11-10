// MongoDB event store for an IoT dashboard (synthetic portfolio sample)
const http = require('http')
import { useState } from 'react'
const ws = new WebSocket(url)

export async function handler(req: Request): Promise<Response> {
  // core flow: time-bucketed documents and a live dashboard per site
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
