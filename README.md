# VANTAGE

**AI-Powered Portfolio Risk & Quantitative Research Platform**

VANTAGE is a read-only portfolio analytics project for rigorous quantitative engineering and applied AI research. Phases 1–3 provide portfolio analytics, advanced quantitative risk, stress testing, reproducible saved runs and controlled volatility forecasting research; later phases add investigations and optimization. Financial results come from tested Python calculations, never an LLM.

## Implemented scope

- Credential-free Demo Mode with versioned, deterministic **synthetic** INR securities and 505 daily price observations per security.
- Portfolio valuation, weights, sector exposures, unrealized P&L, largest-position concentration, and HHI.
- Aligned daily return scenarios; annualized realized volatility; 95%/99% inverse-ECDF historical VaR; scenario drawdown; sample covariance/correlation; 21-day rolling volatility.
- FastAPI with typed responses, structured errors, request IDs, SQLAlchemy persistence, Alembic migrations, and session-owned history imports.
- CSV/Parquet ingestion with source, currency, adjustment, date, size, row, and coverage validation.
- Official Kite Python SDK: server-side authorization, session-bound single-use login state, read-only holdings/positions/margins/instruments, token expiry handling, and disconnect.
- Additional APIs: Alpha Vantage adjusted histories with explicit venue mapping; FRED observations with vintage metadata; Frankfurter daily FX reference rates. Optional providers never block Demo Mode.
- Next.js dark dashboard with working portfolio/source selection, confidence/window controls, risk/sector charts, holdings search/sort, imports, context retrieval, visible errors, and JSON risk-run export.
- Local startup, PostgreSQL Compose deployment configuration, numerical/API/security tests, browser workflow tests, and GitHub Actions.

**Planned:** optimization, document retrieval, LangGraph investigations, and investigation reports. These are not presented as working features. See [roadmap](docs/roadmap.md).

## Phase 2 — advanced quantitative risk

- Historical, analytical Gaussian and correlated Gaussian Monte Carlo **VaR and Expected Shortfall**, with validated custom confidence from 90% to 99.5%.
- Fractional empirical ES tail mass; explicit one-day INR loss conventions; daily means and full sample covariance; optional user-selected identity shrinkage with PSD/rank/condition/correction diagnostics.
- Seeded spectral PSD simulation (10,000 default, 2,000–100,000 allowed), interactive P&L histogram, VaR/ES cutoffs, value/return quantiles and conditional Monte Carlo sampling errors.
- Euler marginal/component/percentage volatility contributions, security/sector charts, correlation diagnostics and reconciliation. Negative hedging contributions are retained; undefined zero-risk percentages are null.
- Direct hypothetical broad/sector/security shocks with documented replacement precedence; historical replay from covered adjusted data; exact endpoint validation; explicit synthetic replay in Demo Mode. No hardcoded historical shocks or invented factor exposures.
- Migration 0002 stores immutable owner-scoped snapshots and selected dated price inputs, compact results, source/input hashes, parameters and model/runtime versions. Saved runs can be listed, opened, compared and replayed without current provider access.
- Existing overview, portfolio, sources, broker/authentication and legacy risk endpoints remain functional. Phase 3 extends these interfaces without adding trading.

### Upgrade and demonstrate

After pulling this version, stop any older backend/frontend processes, apply the migration, and restart using the commands below. Install the current locked dependencies before migration; Phase 3 adds ARCH, LightGBM and SciPy. macOS requires OpenMP (`brew install libomp`); the backend Docker image installs Linux libgomp1.

```bash
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
```

1. Open Demo Mode, then **Risk Analytics**. Keep the existing historical charts or use **Advanced quantitative risk → Calculate and save**.
2. Adjust confidence, seed, simulation count or covariance policy; compare all three VaR/ES estimates. Inspect the distribution, attribution, numerical uncertainty and audit evidence. Export the saved comparison if desired.
3. Open **Stress Testing**. Run a broad shock, add a sector/security override, and inspect exact applied mappings and reconciled P&L. Switch to synthetic replay, choose the covered fixture window, and run it. Actual pandemic/2022 events are disabled without actual covered market data.
4. Open **Risk Runs**, select 2–4 analyses or scenarios of the same kind, and compare backend-computed deltas. Open a saved result and **Replay saved inputs** to verify input/numerical agreement. Archived outputs retain their original portfolio/parameters, independently of current controls.
5. For real historical replay, authorize Kite and import permitted adjusted histories. A separate older scenario dataset can be chosen; fresh current history is independently required for a one-day risk comparison.

See [Phase 1 audit and Phase 2 plan](docs/phase2_audit.md), [mathematical methodology and worked cases](docs/quant_methodology.md), [API contracts](docs/api_contracts.md), and [verification evidence](docs/verification.md).

## Phase 3 — quantitative research

Open **Quantitative Research → Run controlled experiment** to execute rolling, EWMA, Gaussian GARCH(1,1) and LightGBM forecasts of next-observed-day portfolio variance. Inspect matched-date QLIKE/MSE/MAE, rolling errors, conditional 95/99% VaR exceptions and coverage tests, regimes, saved-prediction TreeSHAP, drift, model roles and experiment history. Download actual artifacts/reports or reproduce saved inputs. Jobs run in a bounded background worker; failures stay visible.

The default executed synthetic experiment has 504 returns, development training through 2026-03-13, validation 2026-03-16–2026-06-05 and 100 final targets 2026-06-08–2026-10-23. Rolling QLIKE **-8.334987** was better than LightGBM **-8.318106** (lower is better). This does not establish real-market superiority; all models had zero 99% exceptions in a short synthetic sample. See the [executed report](docs/research/volatility_model_comparison.md), [Phase 2 audit](docs/phase3_audit.md) and [complete research protocol](docs/research_protocol.md).

```bash
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e backend
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python backend/scripts/research_report.py
```

Restart older app processes after upgrading. The CLI generates evidence from actual model runs and validates reproduction. Browser histories belong to their own session. Optional `MODEL_ARTIFACT_DIR` stores private text/JSON checkpoints (ignored by Git); `BUILD_COMMIT` identifies container revisions. Use a single backend worker. Persist/back up database and artifact storage together. Durable identity/session recovery and distributed scheduling remain future work. Phase 4 agents are not implemented.

## Start locally

Requirements: Python **3.12+** (the locked NumPy/SciPy versions require 3.12+), Node **22+**, npm. Demo requires no API keys or running PostgreSQL instance. Commands below start from the repository root.

```bash
cp .env.example .env
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e backend
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:3000**. Demo Mode is selected by default. The UI requests a session, loads the portfolio and risk API, and plots the resulting data. Use **Risk Analytics** for advanced model comparison, simulation, volatility attribution, rolling volatility, drawdown and correlations; **Portfolio** for search/sort; **Data Sources** for imports and optional integrations. Health: http://localhost:8000/api/health. OpenAPI: http://localhost:3000/api/docs.

Use `localhost:3000` consistently. If using a different browser origin, set `FRONTEND_URL` to that exact origin and restart the backend; mutation requests enforce this setting. Keep `--no-access-log` to prevent callback query tokens appearing in web access logs. Next.js request logging is also disabled.

## PostgreSQL / Docker

```bash
docker compose up --build
```

Compose starts PostgreSQL 17, migrates the database, waits for readiness, and starts backend/frontend. Ports bind to loopback; PostgreSQL is internal. API keys are injected only into the backend. The frontend proxy target is baked at build time as `http://backend:8000`. Stop with `docker compose down`; add `-v` only if you deliberately want to delete stored datasets and risk audit records.

For local Python development against PostgreSQL:

```bash
docker compose -f docker-compose.yml -f infra/compose.db-local.yml up -d db
export DATABASE_URL='postgresql+psycopg://vantage:vantage_local_only@127.0.0.1:55432/vantage'
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
```

Change the password in the URL if you changed `POSTGRES_PASSWORD`. SQLite is a convenience fallback, not the deployment database. Migrations are explicit; the app never silently creates tables.

## Kite Mode

1. Create an authorized app in the official Kite developer console. Configure its redirect URL as `http://localhost:3000/api/auth/kite/callback` (or the corresponding HTTPS origin).
2. Set `KITE_API_KEY` and `KITE_API_SECRET` in the root `.env`, restart the backend.
3. Open **Data Sources → Connect Zerodha** and authenticate on Zerodha's official site.
4. Select **Kite · Authorized account**. Holdings load read-only. The browser never receives broker access tokens or secrets.
5. Import permitted, adjusted INR history for every holding and select that dataset. Without complete eligible history, holdings remain visible and risk displays an explicit error.

No order execution routes exist. Kite Personal access does not imply historical/streaming entitlement; this app never requests those endpoints. Tokens live in backend memory for at most 12 hours, may expire earlier at Zerodha, and disappear on restart. Run **one backend worker**. Disconnect clears local broker access and attempts remote revocation. Production multi-user identity and encrypted shared sessions are future work.

## Historical data and additional APIs

CSV/Parquet requires exactly these columns:

```csv
date,instrument,close,currency
2026-01-01,NSE:SYMBOL,123.45,INR
2026-01-02,NSE:SYMBOL,124.10,INR
```

This illustrates the schema; these two invented rows are insufficient for risk. Supply at least 61 observations per holding (101 for 99% risk, 201 for 99.5%), exactly aligned dates, strictly positive finite prices, explicit source/permissions, and confirmed split/dividend adjustment. History must end within seven calendar days of the snapshot and cannot extend beyond it. Maximum file size 5 MB / 50,000 rows / 50 instruments. Unknown or unadjusted imports cannot produce risk. Session ownership controls access; a browser restart/server restart may require importing again. Real data is never merged with demo fixtures.

- **Alpha Vantage:** set `ALPHA_VANTAGE_API_KEY` with adjusted-daily endpoint entitlement. In Data Sources, enter an explicit mapping such as `{"BSE:RELIANCE":"RELIANCE.BSE"}` and attest currency, venue, identity and permissions. Do not map BSE prices to an NSE holding. Missing coverage, subscription limits or rate limits produce errors; no partial dataset is persisted. The adapter requests full adjusted daily history; oversized histories are rejected by import limits.
- **FRED:** set `FRED_API_KEY`. Fetch VIX, Treasury yields or federal funds observations. The API also accepts an explicit `vintage` date. Missing values remain null, and observation/vintage dates are retained. Context is excluded from risk and ML features.
- **Frankfurter:** no key needed. Fetch USD/EUR/GBP to INR daily reference rates in Data Sources. Observed date and provider attribution are shown. Context is cached for one hour and excluded from portfolio valuation.

All providers require network access; optional live services can fail independently. Review [source policy and official links](docs/data_sources.md) before using real data.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `DATABASE_URL` | SQLite locally; PostgreSQL URL in Compose |
| `FRONTEND_URL` | `http://localhost:3000`; exact permitted browser origin and callback destination |
| `BACKEND_URL` | `http://127.0.0.1:8000`; Next.js server proxy target, rebuild production after changing |
| `COOKIE_SECURE` | `false` locally; use `true` under HTTPS |
| `KITE_API_KEY`, `KITE_API_SECRET` | Optional backend-only broker credentials |
| `ALPHA_VANTAGE_API_KEY` | Optional backend-only adjusted-history credential |
| `FRED_API_KEY` | Optional backend-only macro credential |
| `POSTGRES_PASSWORD` | Compose local password; replace for any nonlocal environment |

Phase 2 needs no additional credentials. No secret uses the `NEXT_PUBLIC_` prefix. Do not commit `.env` or private data.

## Validate

```bash
backend/.venv/bin/ruff check backend data/sample/generate.py
backend/.venv/bin/ruff format --check backend data/sample/generate.py
backend/.venv/bin/pytest -c backend/pyproject.toml backend/tests -q
cd frontend
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Apply the database migration before browser tests. Playwright starts backend and production frontend automatically, or reuses healthy local servers. The suite assumes optional provider keys are unset. Set `VANTAGE_PYTHON` if your Python interpreter is elsewhere; `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` can use an installed Chrome instead of downloading Chromium. CI runs numerical/API/security tests, a PostgreSQL-backed migration and risk smoke test, frontend checks, and browser workflows. Live Kite/Alpha Vantage/FRED credentials are intentionally not embedded in tests; their request/response and failure contracts use explicit mocks.

Regenerate the deterministic demo with `backend/.venv/bin/python data/sample/generate.py`; review and commit fixture changes together. Browser artifacts are ignored. See [verification notes](docs/verification.md) for the checks actually executed in this development session.

## Quantitative interpretation and limits

Volatility uses sample standard deviation and 252 observed days/year. Historical VaR uses the inverse empirical CDF of **loss = −return**, at a **one-trading-day** horizon. All-gain samples can legitimately have negative VaR. The displayed path applies today's weights to past adjusted returns and is **not actual historical account performance**. Numbers include window, confidence, sample size, source and as-of metadata. See [formulas and assumptions](docs/quant_methodology.md).

Holdings analysis excludes cash, derivatives, margin funding, positions, execution costs, taxes and liquidity. Kite sector data is Unknown. Uploaded adjustment, data permissions, security mappings, and continuity are user assertions; the application cannot independently certify them. VaR does not bound maximum possible loss or guarantee future coverage. Risk-minimizing investment recommendations remain planned.

Private saved runs currently belong to their initiating active browser session. Server restart or expiry invalidates that session; durable identity/recovery is planned. Stored rows remain private and are not reassigned to new sessions. Historical calendar continuity and adjustment status remain source assertions; named market events require genuine coverage. Monte Carlo sampling noise does not include historical parameter uncertainty or model risk.

The application is designed for local single-user research. Public deployment requires identity, rate limiting, TLS, durable encrypted sessions, retention, backups and audit authorization. [Security boundary](docs/security.md).

## Repository

```text
backend/app/   API, broker, history, provider, persistence, pure risk modules
backend/tests/ independent financial cases, API workflows, auth and adapter tests
frontend/      Next.js App Router, TypeScript, Tailwind CSS, Recharts, TanStack Query
data/sample/   versioned synthetic fixture and generator
data/schemas/  historical data schema
docs/          architecture, methodology, sources, contracts, roadmap, security
infra/         local PostgreSQL development override
.github/       verification workflow
```

Architecture: Browser → Next.js same-origin proxy → FastAPI → pure numerical engine / read-only broker / independent providers → SQLAlchemy/PostgreSQL, with immutable snapshot/input artifacts for Phase 2 replay. [Architecture and plan](docs/architecture.md). Project conventions: [AGENTS.md](AGENTS.md).
