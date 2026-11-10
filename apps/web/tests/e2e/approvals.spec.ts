import { expect, test } from '@playwright/test'
import { draftAndOpenStudio, register, topUp } from './helpers'

test.beforeEach(async ({ request }) => { await topUp(request, 'ml_engineer') })

test('approving a proposal shows evidence on hover and submits it', async ({ page }) => {
  await register(page)
  await draftAndOpenStudio(page, 'j-00001')
  const claim = page.getByTestId('claim').first()
  await claim.hover()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await expect(page.getByTestId('connects-cost')).toBeVisible()
  await page.getByTestId('approve').click()
  await expect(page.getByTestId('decision-done')).toContainText('Approved')
  await page.goto('/pipeline')
  await expect(page.getByTestId('kanban')).toContainText('submitted', { timeout: 60_000 })
})

test('rejecting a proposal requires and keeps a reason', async ({ page }) => {
  await register(page)
  await draftAndOpenStudio(page, 'j-00003')
  await page.getByTestId('reject').click()
  await expect(page.getByTestId('confirm-reject')).toBeDisabled()
  await page.getByTestId('reject-reason').fill('client budget too low')
  await page.getByTestId('confirm-reject').click()
  await expect(page.getByTestId('decision-done')).toContainText('Rejected')
})

test('editing a draft sends the edit back through compliance before approval', async ({ page }) => {
  await register(page)
  await draftAndOpenStudio(page, 'j-00008')
  await page.getByRole('tab', { name: 'Edit' }).click()
  const editor = page.getByTestId('draft-editor')
  await editor.fill((await editor.inputValue()).replace(/^[^.]*\.\s*/, '') + ' Email me at someone@example.com.')
  await page.getByTestId('approve-edit').click()
  await expect(page.getByTestId('decision-done')).toContainText('compliance re-check')
  // the edited text comes back for a final approval with the contact details removed
  await page.goto('/approvals')
  const review = page.getByRole('link', { name: 'Review' }).first()
  await expect(review).toBeVisible({ timeout: 60_000 })
  await review.click()
  await expect(page.getByTestId('claims-view')).not.toContainText('someone@example.com')
})
