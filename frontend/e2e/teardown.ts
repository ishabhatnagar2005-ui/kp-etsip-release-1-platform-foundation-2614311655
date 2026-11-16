import { execFileSync } from 'node:child_process';

// Drop only the database generated for this Playwright invocation.
export default function teardown() {
  const database = process.env.E2E_MONGODB_DB;
  if (!database || process.env.E2E_RUN_OWNER_PID !== String(process.pid) || database !== process.env.E2E_GENERATED_MONGODB_DB || !/^etsip_e2e_[a-f0-9]{16}$/.test(database)) {
    throw new Error('Refusing to drop a database that was not generated for this E2E run');
  }

  execFileSync(process.env.E2E_PYTHON || 'python3', ['-c', `
import os
from pymongo import MongoClient

client = MongoClient(os.environ['E2E_MONGODB_URI'], serverSelectionTimeoutMS=10000)
try:
    client.drop_database(os.environ['E2E_MONGODB_DB'])
finally:
    client.close()
`], {
    env: { ...process.env, E2E_MONGODB_URI: process.env.E2E_MONGODB_URI || 'mongodb://127.0.0.1:27017' },
    stdio: 'inherit',
  });
}
