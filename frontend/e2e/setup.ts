import { chromium, expect, type FullConfig } from '@playwright/test';

// The managed backend seeds a first-use administrator in an isolated database.
// Complete first-use setup through the same UI as a real administrator.
export default async function setup(config: FullConfig) {
  const { baseURL, launchOptions, headless, channel } = config.projects[0].use;
  const browser = await chromium.launch({ ...launchOptions, headless, channel });
  try {
    const page = await browser.newPage({ baseURL });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto('/login');
    await page.getByLabel('Email address').fill('admin@ketsip.local');
    await page.getByLabel('Password').fill(process.env.E2E_ADMIN_INITIAL_PASSWORD!);
    const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in' }).click();
    expect((await login).status()).toBe(200);
    await expect(page.getByText('Change your initial administrator password before accessing other features.')).toBeVisible();
    await page.getByLabel('Current password').fill(process.env.E2E_ADMIN_INITIAL_PASSWORD!);
    await page.getByLabel('New password').fill(process.env.E2E_ADMIN_PASSWORD!);
    const changed = page.waitForResponse(r => r.url().endsWith('/api/auth/password') && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Change password' }).click();
    expect((await changed).status()).toBe(204);
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    expect(errors).toEqual([]);
    // Capture source-level accessibility, styles and HTML before journey execution.
    const preflight = await import('./preflight');
    await preflight.main();
  } finally {
    await browser.close();
  }
}
