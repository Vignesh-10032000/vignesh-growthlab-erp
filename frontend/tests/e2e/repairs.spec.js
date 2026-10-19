import { test, expect } from '@playwright/test'

const api = 'http://127.0.0.1:8001/api/v1'
async function login(page, role = 'super_admin') {
  await page.goto('/login')
  await page.getByPlaceholder('Enter your username').fill(role === 'super_admin' ? 'superadmin' : `repair_${role}`)
  await page.getByPlaceholder('Enter your password').fill(role === 'super_admin' ? 'Admin@1234' : 'RepairPass@123')
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/5197\/$/)
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', response => { if (response.url().includes('/api/') && response.status() >= 500) errors.push(`${response.status()} ${response.url()}`) })
  page._repairErrors = errors
})
test.afterEach(async ({ page }) => { expect(page._repairErrors).toEqual([]) })

test('demo login and notification inbox survive reload', async ({ page }) => {
  await login(page)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Notifications' })).toBeVisible()
})

test('regular admin cannot see profit reports or opening balances', async ({ page }) => {
  await login(page, 'admin')
  await page.goto('/reports')
  await expect(page.getByRole('button', { name: 'P&L', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Clearance', exact: true })).toHaveCount(0)
  await page.goto('/settings/opening-balance')
  await expect(page).toHaveURL(/5197\/$/)
})

test('saved page restrictions deny direct navigation', async ({ page, request }) => {
  const auth = await request.post(api + '/auth/login', { data: { username: 'superadmin', password: 'Admin@1234' } })
  const headers = { Authorization: `Bearer ${(await auth.json()).access_token}` }
  const users = await request.get(api + '/settings/users-permissions', { headers })
  const sales = (await users.json()).find(user => user.username === 'repair_sales')
  await request.put(api + `/settings/users-permissions/${sales.id}`, { headers, data: { page_permissions: ['dashboard', 'billing'] } })
  try {
    await login(page, 'sales')
    await page.goto('/reports')
    await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible()
    await page.goto('/billing/new')
    await expect(page.getByRole('heading', { name: 'Access restricted' })).toHaveCount(0)
    await expect(page.getByText('New Invoice', { exact: true }).first()).toBeVisible()
  } finally {
    await request.put(api + `/settings/users-permissions/${sales.id}`, { headers, data: { page_permissions: null } })
  }
})

test('opening stock page submits through the canonical API', async ({ page, isMobile }) => {
  await login(page)
  await page.goto('/settings/opening-balance')
  await expect(page.getByRole('heading', { name: 'Opening Balance Entry' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import CSV', exact: true })).toBeVisible()
  await page.locator('select').nth(0).selectOption(isMobile ? '2024-25' : '2025-26')
  await page.locator('select').nth(1).selectOption('30')
  await page.locator('select').nth(2).selectOption('1')
  const stock = page.locator('.form-section').filter({ hasText: 'Opening Stock' })
  await stock.locator('input[type="number"]').nth(0).fill('2')
  await stock.locator('input[type="number"]').nth(1).fill('100')
  const response = page.waitForResponse(r => r.url().endsWith('/api/v1/opening-balances/') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save All Opening Balances' }).click()
  expect((await response).status()).toBe(201)
  await expect(page.getByRole('heading', { name: 'Opening Balances Saved' })).toBeVisible()
})

test('SMTP settings load and persist without exposing the saved password', async ({ page }) => {
  await login(page)
  await page.goto('/bank-statement')
  await page.getByRole('button', { name: 'Notifications', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'SMTP Configuration' })).toBeVisible()
  const password = page.locator('input[type="password"]')
  await expect(password).toHaveValue('')
  await expect(password).toHaveAttribute('placeholder', 'Saved password (leave blank to keep)')
  await page.getByRole('button', { name: 'Save SMTP Settings' }).click()
  await expect(page.getByText('Notification settings saved', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Scheduled Reports', exact: true }).click()
  await expect(page.getByText('Reports run in the ERP scheduler', { exact: false })).toBeVisible()
})
