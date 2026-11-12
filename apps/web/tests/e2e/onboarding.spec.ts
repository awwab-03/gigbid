import { expect, test } from '@playwright/test'
import { register } from './helpers'

test('onboarding: create an account, choose a persona, land on the empty inbox', async ({ page }) => {
  await register(page, 'data_analyst')
  await expect(page.getByText('No jobs yet')).toBeVisible()
  // settings show the connected GigSim account and an empty memory
  await page.goto('/settings')
  // the header badge is hidden on phones, so check the settings section itself
  await expect(page.locator('p', { hasText: 'GigSim account:' })).toContainText('data_analyst')
  await expect(page.getByTestId('memory')).toContainText('Nothing yet')
})
