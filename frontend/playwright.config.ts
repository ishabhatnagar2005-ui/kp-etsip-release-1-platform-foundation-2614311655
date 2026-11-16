import { randomBytes } from 'node:crypto';
import { defineConfig } from '@playwright/test';

// Generate in the runner, and inherit the same name when its workers load the config.
// Never trust a caller-supplied database name for this destructive test lifecycle.
const owner = process.env.E2E_RUN_OWNER_PID;
if (owner !== String(process.pid) && owner !== String(process.ppid)) {
  process.env.E2E_RUN_OWNER_PID = String(process.pid);
  process.env.E2E_GENERATED_MONGODB_DB = `etsip_e2e_${randomBytes(8).toString('hex')}`;
}
const database = process.env.E2E_GENERATED_MONGODB_DB;
if (!database || !/^etsip_e2e_[a-f0-9]{16}$/.test(database)) {
  throw new Error('Invalid generated E2E database name');
}
process.env.E2E_MONGODB_DB = database;
process.env.E2E_PYTHON ||= 'python3';
process.env.E2E_ADMIN_INITIAL_PASSWORD ||= randomBytes(24).toString('hex');
process.env.E2E_ADMIN_PASSWORD ||= randomBytes(24).toString('hex');
process.env.E2E_DEMO_PASSWORD ||= randomBytes(24).toString('hex');
process.env.E2E_AUDITOR_PASSWORD = process.env.E2E_DEMO_PASSWORD;
process.env.E2E_JWT_SECRET ||= randomBytes(32).toString('hex');

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/setup.ts',
  globalTeardown: './e2e/teardown.ts',
  workers: 1,
  timeout: 60_000,
  reporter: [['json', { outputFile: 'e2e-results.json' }], ['list']],
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    {
      command: 'cd ../backend && PYTHONPATH=. "$E2E_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/docs',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        E2E_PYTHON: process.env.E2E_PYTHON,
        MONGODB_URI: process.env.E2E_MONGODB_URI || 'mongodb://127.0.0.1:27017',
        MONGODB_DB: process.env.E2E_MONGODB_DB,
        JWT_SECRET: process.env.E2E_JWT_SECRET,
        ADMIN_PASSWORD: process.env.E2E_ADMIN_INITIAL_PASSWORD,
        DEMO_PASSWORD: process.env.E2E_DEMO_PASSWORD,
        CORS_ORIGINS: 'http://127.0.0.1:5173',
        SEED_ON_STARTUP: 'true',
      },
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173/',
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_PROXY_TARGET: 'http://127.0.0.1:8000', VITE_API_BASE_URL: '' },
    },
  ],
});
