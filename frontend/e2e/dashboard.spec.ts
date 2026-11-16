import { expect, test } from '@playwright/test';

test('executive navigates to filtered live dashboard metrics', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  const password = process.env.E2E_DEMO_PASSWORD;
  if (!password) throw new Error('Set E2E_DEMO_PASSWORD to the seeded demo password');
  await page.goto('/login');
  await page.getByLabel('Email address').fill('executive@ketsip.local');
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible();
  const dashboard = page.waitForResponse(response => response.url().endsWith('/api/dashboard/executive') && response.request().method() === 'GET');
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  const first = await dashboard;
  expect(first.status()).toBe(200);
  const data = await first.json();
  expect(data.totalApplications).toBeGreaterThan(0);
  const cards = page.getByRole('region', { name: 'Executive metrics' });
  await expect(cards.getByText(String(data.enterpriseQualityScore), { exact: true }).first()).toBeVisible();
  const filtered = page.waitForResponse(response => response.url().includes('/api/dashboard/executive?') && new URL(response.url()).searchParams.get('riskLevel') === 'High');
  await page.getByLabel('Risk level').selectOption('High');
  const result = await filtered;
  expect(result.status()).toBe(200);
  const high = await result.json();
  expect(high.applicationsAtRisk).toBe(high.totalApplications);
  await expect(cards.getByText(String(high.totalApplications), { exact: true }).first()).toBeVisible();
  await expect(page).toHaveURL(/riskLevel=High/);
  expect(errors).toEqual([]);
});
