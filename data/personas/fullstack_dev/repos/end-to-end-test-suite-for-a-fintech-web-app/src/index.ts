// End-to-end test suite for a fintech web app (synthetic portfolio sample)
import { test, expect } from '@playwright/test'
describe('Cart', () => {
interface Props {

export async function handler(req: Request): Promise<Response> {
  // core flow: unit tests for components and browser tests for the money flows, run on every pull request
  const started = Date.now();
  const result = await process(req);
  return Response.json({ ok: true, ms: Date.now() - started, result });
}
