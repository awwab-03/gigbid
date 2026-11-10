import { expect, test } from '@playwright/test'
import { ADMIN, GIGSIM, register } from './helpers'

test('degraded mode: a marketplace outage shows the banner, recovery clears it', async ({ page, request }) => {
  await register(page)
  await request.post(`${GIGSIM}/admin/chaos`, { headers: ADMIN, data: { outage: true } })
  try {
    await page.reload()
    await expect(page.getByTestId('degraded-banner')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('degraded-banner')).toContainText('queued')
  } finally {
    await request.post(`${GIGSIM}/admin/chaos`, { headers: ADMIN, data: { outage: false } })
  }
  await expect(page.getByTestId('degraded-banner')).toBeHidden({ timeout: 30_000 })
})
