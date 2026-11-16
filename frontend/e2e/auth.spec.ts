import { expect, test } from '@playwright/test';

test('sign in, save a preference, and sign out', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const password = process.env.E2E_DEMO_PASSWORD;
  if (!password) throw new Error('Set E2E_DEMO_PASSWORD to the configured demo password');
  await page.goto('/login');
  await page.getByLabel('Email address').fill('engineer@ketsip.local');
  await page.getByLabel('Password').fill(password);
  const signedIn = page.waitForResponse(response => response.url().endsWith('/api/auth/login') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in' }).click();
  expect((await signedIn).status()).toBe(200);
  await page.getByRole('link', { name: 'My Profile' }).click();
  await expect(page.getByText('engineer@ketsip.local')).toBeVisible();
  await page.getByLabel('Default landing page').selectOption('applications');
  await page.getByRole('button', { name: 'Save preference' }).click();
  await expect(page.getByRole('status')).toContainText('saved');
  await page.reload();
  await expect(page.getByLabel('Default landing page')).toHaveValue('applications');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  expect(errors).toEqual([]);
});
