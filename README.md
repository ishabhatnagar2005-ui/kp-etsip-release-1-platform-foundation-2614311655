# KP ETSIP

KP ETSIP is an internal quality inventory and insight application. It includes six feature areas:

1. Local sign-in, profile, landing preference and password change.
2. Portfolio management and scoped portfolio access.
3. Application inventory, editing and filtering.
4. An executive dashboard with filtered quality and risk aggregates.
5. User and role administration and audit viewing/export.
6. Portfolio and application reports with CSV export.

## Stack

The frontend uses React 18.3.1, React Router 7.18.5, TypeScript 5.8.3, Vite 6.4.6 and Tailwind CSS 3.4.17. The backend uses Python 3.12, FastAPI 0.115.12, Pydantic 2.11.4 and async PyMongo 4.12.1 with MongoDB 8.0. Dependencies are pinned in `frontend/package.json` and `backend/requirements.txt`; container base images are specified in the Dockerfiles and Compose file.

## Local development

Start a real MongoDB server reachable at `mongodb://127.0.0.1:27017`, or configure a secured remote MongoDB URI. Create a Python virtual environment and install the backend dependencies:

```sh
python3 -m venv --copies "$HOME/venvs/etsip"
"$HOME/venvs/etsip/bin/pip" install -r backend/requirements.txt
cp backend/.env.example backend/.env
```

Edit `backend/.env` before starting. Generate three separate random values, for example by running the following command three times, and set `JWT_SECRET`, `ADMIN_PASSWORD` and `DEMO_PASSWORD` respectively:

```sh
"$HOME/venvs/etsip/bin/python" -c 'import secrets; print(secrets.token_hex(24))'
```

Use a unique random JWT secret of at least 32 characters and distinct passwords of 12–72 UTF-8 bytes. Example secrets are rejected; keep `.env` private. Set `MONGODB_URI`, `MONGODB_DB` and comma-separated `CORS_ORIGINS` for your environment. `SEED_ON_STARTUP=false` disables seeding. Startup requires a reachable MongoDB and valid secrets.

Start the API from the backend directory so its `.env` is loaded:

```sh
cd backend
PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m uvicorn app.main:app --reload
```

In another terminal start the frontend:

```sh
cd frontend
npm ci --no-bin-links
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:8000` by default. Set `VITE_PROXY_TARGET` in the frontend process environment to change the proxy target. `frontend/.env.example` documents `VITE_API_BASE_URL` for a different browser API origin; configure backend CORS accordingly.

## Seeded accounts

With seeding enabled, sign in as `admin@ketsip.local` using `ADMIN_PASSWORD`. The `executive`, `leader`, `engineer`, `auditor` and `readonly` accounts at `ketsip.local` use `DEMO_PASSWORD`. The initial administrator must change the password in My Profile before accessing other features and then sign in again. Password changes and logout invalidate previous tokens. Seeding inserts missing identities but does not reset existing passwords; changing the environment values does not rotate existing accounts.

## Tests

Backend tests require a real MongoDB server at `MONGODB_URI` (default `mongodb://127.0.0.1:27017`). They create and drop uniquely named test databases: use a dedicated development/test server, never production. Commands below start from the repository root.

**Unit/service and frontend component tests:**

```sh
(cd backend && PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m pytest -q tests/test_auth_service.py)
(cd frontend && npm test)
```

**API tests:**

```sh
(cd backend && PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m pytest -q tests/test_auth.py tests/test_portfolios.py tests/test_applications.py tests/test_dashboard.py tests/test_admin.py tests/test_reports.py)
```

After the unit/API test critic review is complete, run **cross-feature integration tests**:

```sh
(cd backend && PYTHONPATH=. "$HOME/venvs/etsip/bin/python" -m pytest -q tests/test_integration.py)
```

After the critic review and source-level preflight, run the final **E2E** suite against a dedicated real MongoDB server. Install Chromium if needed. Playwright starts its own backend and frontend on ports 8000 and 5173, generates credentials and a uniquely named test database, and drops that database during teardown; those ports must be free. Set `E2E_MONGODB_URI` if the test server is not local. Do not run against production.

```sh
cd frontend
node node_modules/@playwright/test/cli.js install chromium
E2E_PYTHON="$HOME/venvs/etsip/bin/python" node node_modules/@playwright/test/cli.js test
```

## Build and deployment

Build the production frontend with `cd frontend && npm run build`; it type-checks and writes `frontend/dist`. For the container stack, configure `backend/.env` as above and run from the repository root:

```sh
docker compose up --build -d
```

Open `http://localhost:8080`. Compose builds the frontend and backend, runs MongoDB and persists its data in the `mongo-data` named volume. The included Compose setup is for local development, not a hardened production deployment: MongoDB has no authentication, and the frontend is plain HTTP. For deployment, secure database access, manage secrets and backups, and terminate TLS at an external proxy.

## Operational limitations

- Quality, health, automation, defect and risk values are entered manually in the application inventory. Dashboard and report aggregates derive from those values; there are no automated external integrations collecting them.
- Administrator account changes use a renewable 600-second MongoDB lease, not a fenced lock or transaction. A worker paused longer than the lease after its final check can race a recovered owner; do not treat this as a strict concurrency guarantee.
- Standalone MongoDB writes and audit events are not transactional together. A failure between a change and its audit write can leave an incomplete audit trail; operational reconciliation is necessary where audit completeness matters.
