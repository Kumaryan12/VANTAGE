# Phase 1 verification

Checked locally on 2026-10-26 with Python 3.12, Node 26, Chrome, and PostgreSQL 17 in Docker. CI targets Python 3.12 and Node 22.

| Check | Actual result |
| --- | --- |
| `pytest -c backend/pyproject.toml backend/tests -q` | **51 passed**; one upstream Starlette TestClient/httpx deprecation warning |
| `ruff check backend data/sample/generate.py` | Passed |
| `ruff format --check backend data/sample/generate.py` | Passed |
| `pip check` | No broken requirements |
| Frontend ESLint | Passed |
| Frontend TypeScript | Passed |
| Next.js production build | Passed |
| Playwright, `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **3 passed** against real backend/frontend processes |
| PostgreSQL Alembic migration | Applied successfully |
| PostgreSQL-backed readiness, demo portfolio/risk, import, ownership listing, audit persistence | Passed |
| Frankfurter live provider request | Passed with observed/retrieved dates retained |
| Frankfurter live fetch through browser → Next.js → backend | Passed; no uncaught browser errors |
| Desktop and mobile screenshots | Reviewed; 390 px document width at a 390 px viewport |
| `docker compose config --quiet` | Passed |
| Complete Compose backend/frontend image build | Not executed; local startup and containerized PostgreSQL tested |

Browser workflows cover source selection, 95%/99% confidence, window changes, charts/correlations, risk-run JSON download, holding search, account authentication errors without demo fallback, missing FRED-key errors, historical imports, and mobile navigation. An explicit query-parameter regression discovered by the browser suite now has four backend tests.

Browser verification uses a clean session and no broker or keyed-provider credentials. The optional `PLAYWRIGHT_CHANNEL=chrome` uses installed Chrome; CI uses the preinstalled Chrome on the pinned Ubuntu 24.04 runner. Screenshots are local ignored artifacts at `artifacts/overview.png`, `artifacts/risk.png`, `artifacts/sources.png`, and `artifacts/mobile.png`.

GitHub Actions runs backend checks with a PostgreSQL smoke test and frontend checks with browser tests. Remote execution logs are the source of truth for CI outcomes.

Live broker and keyed-provider access require the owner's credentials and entitlements. Mock contract tests do not imply a successful live authorization or licensed data retrieval.

## Phase 2 verification — 2026-10-26

Phase 1 was audited before modification at `73fcd8e`: 51 Python tests, backend lint/format, frontend lint/type checks and production build passed. The Phase 1 browser suite remains included in the complete six-workflow suite.

| Phase 2 check | Actual outcome |
| --- | --- |
| `pytest -c backend/pyproject.toml backend/tests -q` | **133 passed**; same single upstream TestClient/httpx deprecation warning |
| Ruff lint and format | Passed, including numerical modules, schemas, services, migration, tests and PostgreSQL smoke script |
| Frontend ESLint / TypeScript / Next.js production build | Passed |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **6 passed**: three Phase 1 regressions plus advanced comparison/archive/replay, stress/replay and advanced mobile layout |
| SQLite migration 0001 → 0002 → 0001 | Passed in an isolated temporary database; legacy row preserved |
| Existing SQLite and PostgreSQL migration to 0002 | Applied successfully |
| PostgreSQL-backed Phase 1/2 smoke | Passed: readiness, legacy risk, advanced analysis, ownership/listing/comparison, immutable input storage, exact analysis and synthetic-stress replay |
| Numerical known cases | Passed: inverse-ECDF VaR, fractional/tied empirical ES, tabulated Gaussian VaR/ES, correlated/uncorrelated/concentrated/zero/singular portfolios, negative Euler components, shrinkage and PSD corrections |
| Monte Carlo validation | Fixed-seed equality passed; N=100,000 correlated Gaussian estimates within six conditional asymptotic SEs of analytical VaR/ES; histogram/quantile invariants passed |
| Stress reconciliation | Security and sector P&L sums reconcile; replacement precedence and exact endpoint requirements tested |
| Authorization / integrity | Cross-session retrieval/comparison/replay denied; source/artifact/parameter tampering rejected; broker authorization and real/demo separation preserved |
| Desktop/mobile visual inspection | Model cards, P&L histogram/cutoffs, security/sector attribution and stress output reviewed; no uncaught browser errors; document width 390 px at viewport 390 px |
| Complete Compose image stack | Not built; documented local processes and actual PostgreSQL container verified |

The suite uses explicitly synthetic fixtures for numerical and real-mode contract mechanics. No actual historical scenario loss, live Kite authorization, or keyed-provider retrieval is claimed from those tests. Actual historical scenarios require an authorized portfolio and permitted covered history.

The Gaussian regression fixture independently checks 31,897.072539 INR 95% VaR and 40,254.256150 INR ES for V=1,000,000, μ=.001 and σ=.02. The 25-loss illustration checks 23.2 INR ES at 90%; the tied-cutoff case checks VaR=1 and ES=3 rather than naive conditional averaging. Numerical and statistical tolerances are documented in `quant_methodology.md` and test comments.

Ignored visual artifacts: `artifacts/phase2-models.png`, `phase2-distribution.png`, `phase2-attribution.png`, `phase2-stress.png`, and `phase2-mobile-models.png`. Run `DATABASE_URL=… backend/.venv/bin/python backend/scripts/smoke_phase2.py` after migration to reproduce database-backed verification. GitHub Actions now runs that script against PostgreSQL plus the full backend/browser suites.

A startup regression test also verifies that `.env.example` relative SQLite URLs resolve to the same repository database when backend/test processes run from different directories.

Final CI exposed a Linux/OpenBLAS layout-sensitive replay delta in the strict zero-difference smoke assertion. Model patch 2.0.1 canonicalizes row-major float64 return/covariance inputs and stress paths; a C/F-layout regression test and exact original/replay model equality assertion cover this. The smoke assertion remains exactly zero rather than accepting an arbitrary financial tolerance.

CI pins Ubuntu 24.04 and uses its preinstalled Google Chrome with Playwright’s supported `chrome` channel. This follows the same browser path validated locally and removes a system-package/browser download step that stalled on one hosted runner. CI verifies the browser version explicitly before testing; no tests were skipped.

## Phase 3 local verification — 2026-10-26

- Baseline before implementation: 133 backend tests, Ruff, frontend lint/types/build passed; original six browser workflows preserved.
- Final Phase 3 suite: **169 backend tests passed**, including actual ARCH/LightGBM fitting, hand-calculated EWMA/Kupiec/transition examples, future mutation invariance, training-only imputation, expanding/rolling refits, exact seeded prediction vectors and saved-booster/TreeSHAP reconstruction. One existing Starlette/httpx test-client deprecation warning remains.
- **Seven Chrome browser workflows passed**, covering all six Phase 1/2 workflows and actual research jobs, four-model leaderboard, explanations, private artifact/report downloads, selected evaluation windows, reproduction, configuration comparison and 390px mobile overflow checks. Desktop/mobile screenshots were visually reviewed; browser artifacts remain ignored.
- Frontend ESLint, TypeScript generation/check and optimized Next.js build passed. Backend Ruff check/format passed.
- Alembic migration 0003 applied to SQLite and local PostgreSQL 17. The PostgreSQL research smoke executed four real models on 100 matched targets, persisted forecasts/model metadata, reloaded private checkpoints, reconstructed predictions, checked cross-owner denial and reproduced immutable inputs successfully. Existing Phase 1/2 DB smoke remains in CI.
- The default synthetic experiment and its saved-input reproduction ran on SQLite; [the generated report](research/volatility_model_comparison.md) records actual 504-return coverage, training/validation/test dates, hashes/runtime/commit, measured metrics, confidence tests and model selection. Rolling average QLIKE was lower than LightGBM. Bootstrap intervals include zero; high-volatility test regime has no observations and 99% independence is unavailable (zero exceptions). No economic superiority claim follows.
- CI adds the PostgreSQL Phase 3 smoke and automatically includes research browser tests. See the repository Actions run for platform verification; full Compose image builds have not been verified locally. Container configuration adds Linux OpenMP and persistent model storage.

Real Kite authentication and provider entitlements still need user credentials; no claim of newly verified live-market ML data is made. Durable identity, restart recovery, distributed workers, data retention/backup operations and public deployment remain future work. Model and database storage must be retained together.

## Phase 4 verification — 2026-10-26 to 2026-10-27

The baseline at `f8f68aa` passed 169 backend tests, Ruff, frontend lint/types/build, seven browser workflows and PostgreSQL Phase 1–3 smoke checks. A stale local frontend initially failed browser loading after rebuilding; restarting it restored all seven baseline workflows.

- Phase 4 adds actual typed investigator/tool/provider/security/document/evaluation tests while retaining all earlier numerical and adapter tests. The full backend suite passed **188 tests**. Existing Starlette/httpx and synthetic active-PDF fixture deprecation warnings do not affect the outcomes.
- The full **nine Chrome browser workflows passed**: seven legacy workflows plus owner-scoped verified model investigation, missing research, PDF upload/index/search/citation inspection/download, reconciled technology shock, executed golden evaluation, deletion and 390px mobile overflow checks. Desktop screenshots were visually reviewed; browser/PDF artifacts remain ignored.
- SQLite and PostgreSQL migrations 0004/0005 were applied. PostgreSQL executed the real 60-case synthetic golden workflow/probe suite and passed its fixed acceptance thresholds. Existing Phase 1/2 and research persistence/reproduction smoke checks passed; CI includes all three database slices.
- The [executed evaluation report](agent_evaluation_results.md) records 60/60 task cases, 45/45 tool workflows, 24/24 numerical-reference cases, 15/15 citation/retrieval cases and 17/17 safety checks, with real timings and case failures retained. These are deterministic curated development/regression measurements, **not live-LLM accuracy or financial validity**. Tokens/cost are unavailable because no paid call occurs.
- The first development golden run passed 25/60; a shortfall/fall routing defect and inappropriate interactive rate-limiting of the isolated evaluator were fixed without altering expected answers/thresholds. Examples are retained in `data/evaluations/regression_failures_v1.json`; failed runs were not erased.
- GitHub Actions caught a TypeScript browser-test locator named `document` shadowing the browser DOM global. Renaming the locator fixes test type checking; browser execution itself had already passed. Final Actions status is visible in the repository workflow run.
- OpenAI Responses/embedding transport behavior uses explicit mocks, including retry, failure, schema, authorization and unsupported-value checks. Optional paid-provider smoke is implemented separately and has not been executed without configured credentials. No live-provider or live semantic-retrieval quality claim is made.

The Phase 3 report retains its original experiment/runtime provenance. No Phase 5 optimization or trading was introduced. Single-process ephemeral identity, durable recovery/retention, hardened parser sandboxing, global quotas and public-deployment operations remain Phase 6 work. Complete Compose image builds remain unverified; local application and PostgreSQL-backed workflows are the tested deployment paths.
