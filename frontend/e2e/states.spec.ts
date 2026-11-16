import { expect, test, type Page } from '@playwright/test';

function captureErrors(page: Page, allowInvalidLogin = false) {
  const errors: string[] = [];
  let expectedLoginErrors = allowInvalidLogin ? 1 : 0;
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const location = message.location().url;
    // Chromium reports a failed resource for the one deliberately invalid POST.
    if (expectedLoginErrors > 0 && location && new URL(location).pathname === '/api/auth/login' &&
        /^Failed to load resource: the server responded with a status of 401\b/.test(message.text())) {
      expectedLoginErrors--;
      return;
    }
    errors.push(message.text());
  });
  return errors;
}

async function signIn(page: Page, email: string, password: string) {
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  const response = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  expect((await result.json()).user.email).toBe(email);
}

async function changePassword(page: Page, current: string, next: string, onChanged?: () => void) {
  await page.getByLabel('Current password').fill(current);
  await page.getByLabel('New password').fill(next);
  const response = page.waitForResponse(r => r.url().endsWith('/api/auth/password') && r.request().method() === 'PUT');
  await page.getByRole('button', { name: 'Change password' }).click();
  expect((await response).status()).toBe(204);
  onChanged?.();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
}

test('protected entry redirects and invalid credentials show an error', async ({ page }, testInfo) => {
  const errors = captureErrors(page, true);
  await page.goto('/applications');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Email address').fill('engineer@ketsip.local');
  await page.getByLabel('Password').fill('invalid-password-for-journey');
  const failed = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const response = await failed;
  expect(response.status()).toBe(401);
  expect((await response.json()).detail).toBe('Invalid email or password');
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password');
  await page.screenshot({ path: testInfo.outputPath('login-error.png'), fullPage: true });
  await signIn(page, 'engineer@ketsip.local', process.env.E2E_DEMO_PASSWORD!);
  await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('password change requires relogin and restores demo credentials', async ({ page }) => {
  const errors = captureErrors(page);
  const email = 'engineer@ketsip.local';
  const original = process.env.E2E_DEMO_PASSWORD!;
  const temporary = `temporary-${Date.now()}-password`;
  let changed = false;
  await page.goto('/login');
  await signIn(page, email, original);
  await page.getByRole('link', { name: 'My Profile' }).click();
  try {
    await changePassword(page, original, temporary, () => { changed = true; });
    await signIn(page, email, temporary);
    await page.getByRole('link', { name: 'My Profile' }).click();
    await expect(page.getByText(email)).toBeVisible();
  } finally {
    if (changed) {
      if (await page.getByRole('heading', { name: 'Sign in' }).isVisible()) await signIn(page, email, temporary);
      if (!await page.getByLabel('Current password').isVisible()) await page.getByRole('link', { name: 'My Profile' }).click();
      await changePassword(page, temporary, original);
      await signIn(page, email, original);
      await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible();
    }
  }
  expect(errors).toEqual([]);
});

test('loading and empty search reflect real responses', async ({ page }, testInfo) => {
  const errors = captureErrors(page);
  await page.goto('/login');
  await signIn(page, 'executive@ketsip.local', process.env.E2E_DEMO_PASSWORD!);
  await expect(page.getByRole('heading', { name: 'Executive Dashboard' })).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/portfolios*', async route => { await gate; await route.continue(); });
  const listed = page.waitForResponse(r => new URL(r.url()).pathname === '/api/portfolios' && r.request().method() === 'GET');
  try {
    await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
    await expect(page.getByRole('status')).toHaveText('Loading portfolios…');
    await page.screenshot({ path: testInfo.outputPath('portfolios-loading.png'), fullPage: true });
  } finally { release(); }
  const response = await listed;
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.items.length).toBeGreaterThan(0);
  await expect(page.getByRole('link', { name: data.items[0].name, exact: true })).toBeVisible();
  await page.unroute('**/api/portfolios*');
  const query = `no-match-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const filtered = page.waitForResponse(r => new URL(r.url()).pathname === '/api/portfolios' && new URL(r.url()).searchParams.get('search') === query);
  await page.getByLabel('Search').fill(query);
  const empty = await filtered;
  expect(empty.status()).toBe(200);
  expect((await empty.json()).items).toEqual([]);
  await expect(page.getByText('No portfolios found.')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('portfolios-empty.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('mobile dashboard drills down to a real portfolio and application', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = captureErrors(page);
  await page.goto('/login');
  const dashboard = page.waitForResponse(r => new URL(r.url()).pathname === '/api/dashboard/executive');
  await signIn(page, 'executive@ketsip.local', process.env.E2E_DEMO_PASSWORD!);
  const dashboardResponse = await dashboard;
  expect(dashboardResponse.status()).toBe(200);
  const metrics = await dashboardResponse.json();
  const portfolio = metrics.portfolios.find((item: { applicationCount: number }) => item.applicationCount > 0);
  expect(portfolio).toBeTruthy();
  await expect(page.getByRole('region', { name: 'Executive metrics' }).getByText(String(metrics.totalApplications), { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mobile-dashboard.png'), fullPage: true });
  const detail = page.waitForResponse(r => new URL(r.url()).pathname === `/api/portfolios/${portfolio.id}`);
  const applications = page.waitForResponse(r => new URL(r.url()).pathname === `/api/portfolios/${portfolio.id}/applications`);
  await page.getByRole('link', { name: portfolio.name, exact: true }).click();
  expect((await detail).status()).toBe(200);
  const appResponse = await applications;
  expect(appResponse.status()).toBe(200);
  const items = (await appResponse.json()).items;
  expect(items.length).toBeGreaterThan(0);
  await expect(page.getByRole('heading', { name: portfolio.name })).toBeVisible();
  const application = page.waitForResponse(r => new URL(r.url()).pathname === `/api/applications/${items[0].id}`);
  await page.getByRole('link', { name: items[0].name, exact: true }).click();
  const appDetail = await application;
  expect(appDetail.status()).toBe(200);
  const app = await appDetail.json();
  expect(app.portfolioId).toBe(portfolio.id);
  await expect(page.getByRole('heading', { name: app.name })).toBeVisible();
  await expect(page.getByText(app.businessOwner, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mobile-application.png'), fullPage: true });
  expect(errors).toEqual([]);
});
