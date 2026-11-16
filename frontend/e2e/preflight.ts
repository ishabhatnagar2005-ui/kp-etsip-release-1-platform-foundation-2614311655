// Optional reviewer capture against already running services; not a test runner.
// Run from frontend with E2E_DEMO_PASSWORD set to the seeded demo password.
import { chromium, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

async function capture(page: Page, name: string) {
  const tree = await page.locator('body').ariaSnapshot();
  const styles = await page.locator('body').evaluate(body => {
    const elements = [body, ...Array.from(body.querySelectorAll('header, nav, main, h1, button, input, table')).slice(0, 30)];
    return elements.map(element => {
      const style = getComputedStyle(element);
      return { tag: element.tagName, text: (element.textContent || '').trim().slice(0, 100), display: style.display, color: style.color, background: style.backgroundColor, font: style.font, width: style.width, overflow: style.overflow };
    });
  });
  const html = await page.content();
  await writeFile(join('test-results', 'preflight', `${name}.txt`), `ACCESSIBILITY TREE\n${tree}\n\nCOMPUTED STYLES\n${JSON.stringify(styles, null, 2)}\n\nHTML\n${html}`, 'utf8');
  await page.screenshot({ path: join('test-results', 'preflight', `${name}.png`), fullPage: true });
}

export async function main() {
  const password = process.env.E2E_DEMO_PASSWORD;
  if (!password) throw new Error('Set E2E_DEMO_PASSWORD for the seeded executive account.');
  await mkdir(join('test-results', 'preflight'), { recursive: true });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173', viewport: { width: 1440, height: 900 } });
    await page.goto('/login');
    await capture(page, 'desktop-login');
    await page.getByLabel('Email address').fill('executive@ketsip.local');
    await page.getByLabel('Password').fill('deliberately-invalid-password');
    const invalid = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/login' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in' }).click();
    if ((await invalid).status() !== 401) throw new Error('Expected invalid-login response');
    await page.getByRole('alert').waitFor();
    await capture(page, 'desktop-login-error');
    await page.getByLabel('Password').fill(password);
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/dashboard/executive', async route => { await gate; await route.continue(); });
    const dashboard = page.waitForResponse(r => new URL(r.url()).pathname === '/api/dashboard/executive');
    try {
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByText('Loading dashboard…').waitFor();
      await capture(page, 'desktop-dashboard-loading');
    } finally { release(); }
    if (!(await dashboard).ok()) throw new Error('Dashboard request failed');
    await page.unroute('**/api/dashboard/executive');
    await page.getByRole('region', { name: 'Executive metrics' }).waitFor();
    await capture(page, 'desktop-dashboard');
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'mobile-dashboard');
    const list = page.waitForResponse(r => new URL(r.url()).pathname === '/api/portfolios');
    await page.getByRole('link', { name: 'Portfolios', exact: true }).click();
    if (!(await list).ok()) throw new Error('Portfolio request failed');
    await page.getByLabel('Search').fill(`preflight-no-match-${Date.now()}`);
    await page.getByText('No portfolios found.').waitFor();
    await capture(page, 'mobile-empty');
  } finally { await browser.close(); }
}


