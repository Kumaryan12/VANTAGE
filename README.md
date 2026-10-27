# VANTAGE

**AI-Powered Portfolio Risk & Quantitative Research Platform**

VANTAGE is a read-only portfolio analytics project for rigorous quantitative engineering and applied AI research. Phases 1–4 provide portfolio analytics, advanced quantitative risk, stress testing, reproducible forecasting research and evidence-grounded financial investigations; Phase 5 adds constrained decision support; Phase 6 production hardening remains planned. Financial results come from tested Python calculations, never an LLM.

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

**Planned:** Phase 6 production hardening. See [roadmap](docs/roadmap.md).

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

Restart older app processes after upgrading. The CLI generates evidence from actual model runs and validates reproduction. Browser histories belong to their own session. Optional `MODEL_ARTIFACT_DIR` stores private text/JSON checkpoints (ignored by Git); `BUILD_COMMIT` identifies container revisions. Use a single backend worker. Persist/back up database and artifact storage together. Durable identity/session recovery and distributed scheduling remain future work. Phase 4 adds controlled investigations below.

## Phase 4 — AI Risk Assistant

The new terminal runs bounded multistep investigations using **14 authorized tools** wrapping existing portfolio, risk, stress and ML services plus private financial-document retrieval. Financial values, units, dates, source IDs and page quotes are verified deterministically before publication; hypothetical P&L contributions reconcile to the original engine. Model comparison retains synthetic/current-weight/sample/uncertainty qualifications and original experiment provenance. No trading or automatic model promotion is available.

1. Open **AI Risk Assistant**. Without credentials, **AI provider not configured** is explicit; choose **Deterministic demonstration · no LLM** to execute actual backend tools through scripted routing.
2. For model comparison, first run an experiment in **Quantitative Research in the same browser session**, then use the example question or select it. Inaccessible/expired-session experiments produce limitations, never a fallback to someone else's results.
3. Ask **Which holdings contribute most to my portfolio risk?** or use **Sector shock example**. Inspect verified financial tables, saved run IDs, assumptions, ordered activity and evidence. Scenarios are direct hypothetical shocks, not forecasts.
4. Upload a permitted text PDF with source/permission metadata in the **Financial document library**. Wait for ready status, select it as context, and use **Document research example**. Inspect exact cited page passages or download the source. Keyword retrieval needs no AI key; external embeddings require explicit separate consent.
5. **Run golden evaluation** to execute 60 isolated synthetic workflow/security cases and inspect actual checks/failures. These measurements do not establish live-LLM accuracy or real-market validity.

For live AI, set backend-only `OPENAI_API_KEY` and `LLM_MODEL`, restart the backend, choose the configured provider and consent to sending minimized redacted evidence. This repository implements OpenAI Responses with strict function/answer schemas behind a pluggable interface. Provider integration is mock-tested; no paid-provider quality result is claimed without an opt-in actual run. Use one backend process.

```bash
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e backend
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python backend/scripts/agent_evaluate.py
# Optional actual paid-provider smoke, only after deliberately configuring a key:
# VANTAGE_LIVE_AI=1 backend/.venv/bin/python backend/scripts/smoke_live_ai.py
```

Migrations 0004/0005 add owned investigations, steps, tool calls, evidence, evaluations and PDF/chunk indexes. Private PDFs live under `DOCUMENT_STORAGE_DIR`; back up database and both artifact volumes together. Deletion cleans indexes/files and marks old citations unavailable. Session expiry/restart still prevents recovery; parser sandboxing, identity, retention, global quotas and distributed execution remain Phase 6 work.

See [agent architecture/setup](docs/agent_architecture.md), [financial RAG](docs/financial_rag.md), [tool schemas](docs/agent_tool_contracts.md), [evaluation protocol](docs/agent_evaluation.md), [executed results](docs/agent_evaluation_results.md) and [threat model](docs/agent_threat_model.md).

## Phase 5 — portfolio optimization and decision intelligence

- CVXPY/CLARABEL minimum annual variance, variance-plus-turnover/cost penalties, target-risk feasibility, and conditional target-return research with complete explicitly sourced assumptions.
- Long-only fully invested held INR equity sleeve; global/asset/frozen/sector policies, explicit Unknown handling, one-way turnover `.5 Σ|Δw|`, configurable symmetric/asymmetric research costs. Missing cash remains unknown; no real-to-demo fallback or silent constraint relaxation.
- Independently checked solver outcomes and residuals; matched historical/Gaussian/Monte Carlo VaR/ES, signed attribution, concentration and unchanged unfavorable tail-risk results.
- Saved risk–turnover curves, gated return frontier, six-axis sensitivity, identical direct/historical counterfactual stress with immutable scenario replay, and private run comparison/reproduction/export.
- **Portfolio Optimization** dashboard with actual constraint controls, allocation charts/sortable tables, complete risk comparisons, sensitivity/curve point inspection, stress comparison, history and human research governance.
- Candidate → under_review → validated → approved_research (with rejection/retirement paths), eight written assessment areas, reproduction/evidence gates and authorized session review events. No automatic champion or investment-use approval.
- Eight additional pinned agent tools; actual risk-reduction goal assessment and 13 fixed optimization cases alongside the unchanged 60-case investigator suite. No orders, holdings mutation, agent policy relaxation or AI governance writes.

Install current locked dependencies (CVXPY/CLARABEL), apply migrations through **0008**, and restart current backend/frontend processes. Migration 0006 fixes persisted tool-call ordering; 0007 stores optimization/stress aggregates; 0008 stores research model reviews. Existing APIs/migrations remain compatible.

1. In Demo Mode open **Portfolio Optimization**. Select 20% maximum position weight and 15% one-way turnover; run and inspect actual status, risk comparison and residuals.
2. Export, reproduce saved inputs, then try zero turnover to see the conflicting-cap infeasibility. No proposed allocation is invented.
3. Calculate the **risk–turnover curve** and inspect individual points. Run labeled sensitivity variations; exact sector/asset keys are listed in advanced settings. A return frontier stays disabled until complete sourced assumptions are entered.
4. Compare identical sector/direct or exactly covered historical scenarios. Synthetic replay is explicitly labeled and cannot stand for an actual market event.
5. Review the candidate's evidence in **Model governance**. Only explicit human actions, substantive notes and successful reproduction can advance it. All approval scope is methodological research.
6. In **AI Risk Assistant**, select a saved optimization or use the risk-reduction example. The backend assesses actual achieved reduction under the requested turnover cap.

[Methodology](docs/optimization_methodology.md) · [constraints](docs/optimization_constraints.md) · [architecture](docs/optimization_architecture.md) · [governance](docs/model_governance.md) · [executed synthetic report](docs/research/portfolio_optimization_validation.md) · [validation commands](docs/optimization_validation.md).

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
| `OPENAI_API_KEY`, `LLM_MODEL` | Optional backend-only AI key/model; default model `gpt-4.1-mini` |
| `LLM_TIMEOUT_SECONDS` | Bounded provider timeout, default 12 seconds |
| `EMBEDDING_MODEL` | Optional consent-based semantic index, default `text-embedding-3-small` |
| `DOCUMENT_STORAGE_DIR` | Private PDF storage, default `artifacts/documents` |
| `DOCUMENT_CHUNK_CHARS`, `DOCUMENT_CHUNK_OVERLAP` | Page-local text chunking, default 1800/180 |
| `LLM_INPUT_USD_PER_MILLION`, `LLM_OUTPUT_USD_PER_MILLION` | Optional account-specific cost estimates; omitted means unavailable |

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

Holdings analysis excludes cash, derivatives, margin funding, positions, execution costs, taxes and liquidity. Kite sector data is Unknown. Uploaded adjustment, data permissions, security mappings, and continuity are user assertions; the application cannot independently certify them. VaR does not bound maximum possible loss or guarantee future coverage. Phase 5 provides constrained research allocations; it does not establish investment suitability or executable orders.

Private saved runs currently belong to their initiating active browser session. Server restart or expiry invalidates that session; durable identity/recovery is planned. Stored rows remain private and are not reassigned to new sessions. Historical calendar continuity and adjustment status remain source assertions; named market events require genuine coverage. Monte Carlo sampling noise does not include historical parameter uncertainty or model risk.

The application is designed for local single-user research. Public deployment requires identity, rate limiting, TLS, durable encrypted sessions, retention, backups and audit authorization. [Security boundary](docs/security.md).

## Repository

```text
backend/app/   API, broker, history, providers, risk/ML engines, agent and PDF evidence
backend/tests/ independent financial cases, API workflows, auth and adapter tests
frontend/      Next.js App Router, TypeScript, Tailwind CSS, Recharts, TanStack Query
data/sample/   versioned synthetic market fixture and generator
data/evaluations/  curated 60-case agent dataset and retained regression failures
data/schemas/  historical data schema
docs/          architecture, methodology, sources, contracts, roadmap, security
infra/         local PostgreSQL development override
.github/       verification workflow
```

Architecture: Browser → Next.js same-origin proxy → FastAPI → pure numerical engine / read-only broker / independent providers → SQLAlchemy/PostgreSQL, with immutable snapshot/input artifacts for Phase 2 replay. [Architecture and plan](docs/architecture.md). Project conventions: [AGENTS.md](AGENTS.md).
