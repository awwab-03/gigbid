import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const API = 'http://localhost:8001'
export const GIGSIM = 'http://localhost:8082'
export const ADMIN = { 'X-Admin-Token': 'gigsim-admin' }

export async function register(page: Page, account: 'ml_engineer' | 'fullstack_dev' | 'data_analyst' = 'ml_engineer') {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@gigbid.test`
  await page.goto('/login')
  await page.getByRole('tab', { name: 'Create account' }).click()
  await page.getByLabel('Name').fill('E2E Tester')
  await page.getByTestId('email').fill(email)
  await page.getByTestId('password').fill('e2e-password-1')
  const labels = { ml_engineer: 'AI/ML engineer', fullstack_dev: 'Full-stack web developer', data_analyst: 'Data analyst' }
  await page.getByText(labels[account], { exact: true }).click()
  await page.getByTestId('submit').click()
  await expect(page.getByRole('heading', { name: 'Job inbox' })).toBeVisible()
  return email
}

/** Analyse one job from the inbox and wait until the graph pauses for approval, then open the studio. */
export async function draftAndOpenStudio(page: Page, jobId: string) {
  await page.getByTestId('import-id').fill(jobId)
  await page.getByTestId('import').click()
  const review = page.getByRole('link', { name: 'Review' }).first()
  await expect(review).toBeVisible({ timeout: 90_000 })
  await review.click()
  await expect(page.getByRole('heading', { name: 'Proposal studio' })).toBeVisible()
  await expect(page.getByTestId('approval-panel')).toBeVisible()
}

export async function topUp(request: APIRequestContext, account: string) {
  await request.post(`${GIGSIM}/admin/connects?freelancer_id=${account}&balance=1000`, { headers: ADMIN })
}
