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
