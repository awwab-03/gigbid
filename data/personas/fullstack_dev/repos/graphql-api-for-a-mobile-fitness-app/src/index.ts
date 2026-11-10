// GraphQL API for a mobile fitness app (synthetic portfolio sample)
const http = require('http')
interface Props {
import { Module } from '@nestjs/common'

export async function handler(req: Request): Promise<Response> {
  // core flow: a single typed schema with data loaders and field-level auth
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
