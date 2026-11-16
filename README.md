# KP ETSIP — identity foundation

This slice implements local sign-in, profile, landing preference and password change. Inventory and dashboard functionality is not yet implemented; users are taken to My Profile rather than a non-existent landing page. Their saved landing choice is retained for those future features.

## Configuration and local run

Start MongoDB locally (or provide an Atlas URI). Copy `backend/.env.example` to `backend/.env` and replace `JWT_SECRET` with a unique random secret of at least 32 characters and both password values with unique secrets of 12–72 UTF-8 bytes. The example values are intentionally rejected. Keep `.env` private. `MONGODB_DB` selects the database, `CORS_ORIGINS` is comma-separated, and `SEED_ON_STARTUP=false` disables seeding. Startup requires MongoDB and refuses invalid secrets.

```sh
python3 -m venv --copies "$HOME/venvs/etsip"
"$HOME/venvs/etsip/bin/pip" install -r backend/requirements.txt
cd backend
PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m uvicorn app.main:app --reload
```

In another terminal, `cd frontend && npm install --no-bin-links && node node_modules/vite/bin/vite.js`. Vite proxies `/api` to the local backend. Copy `frontend/.env.example` to `.env` if overriding the proxy or API base. Open `http://localhost:5173`. For Docker, create `backend/.env` as above, then `docker compose up --build`; open port 8080. Mongo data is stored in a named volume. Use TLS at the external proxy in deployment and secure MongoDB access; the local compose MongoDB is intended for local development only.

## Demo credentials

The administrator is `admin@ketsip.local`, using the configured `ADMIN_PASSWORD`. Five other local accounts (`executive`, `leader`, `engineer`, `auditor`, `readonly` at `ketsip.local`) use `DEMO_PASSWORD`. Seeding inserts missing identities only and never resets existing passwords. The administrator must change the initial password; the permission guard rejects first-use access to protected future functionality. Profile and password endpoints remain available to complete that change. Password change and logout invalidate previous tokens. Rotating seed environment values does not rotate already-created accounts.

## Tests

With a real MongoDB at `MONGODB_URI` (default localhost), run `cd backend && PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m pytest -q tests/test_auth.py`. The test creates and drops a uniquely named test database. Frontend: `cd frontend && node node_modules/vitest/vitest.mjs run`. The Playwright spec is provided for later execution against running services; configure `E2E_DEMO_PASSWORD` and optionally `E2E_BASE_URL`. Do not run it against a production database: it changes the demo preference.
